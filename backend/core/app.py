"""FastAPI application: upload, queue, status, cancel, SSE and exports."""

from __future__ import annotations

import asyncio
import io
import json
import os
import re
import uuid
import zipfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import exporters
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.audio import ffmpeg_available
from core.config import ENGINE_CHOICES, MODEL_SIZES, POST_PROVIDERS, Settings
from core.diarizer.pyannote import PyannoteDiarizer
from core.job import JobState
from core.pipeline import Pipeline
from core.post.base import build_post_processor
from core.queue import Job, JobRepository
from core.worker import Worker
from engines.base import build_engine

VERSION = "2.0.0"
CHUNK_SIZE = 1024 * 1024


@dataclass
class Components:
    settings: Settings
    engine: Any
    diarizer: Any
    post_processor: Any
    pipeline: Pipeline
    repository: JobRepository
    worker: Worker


def build_components(settings: Settings, start_worker: bool = True) -> Components:
    """Wire engine, diarizer, post-processor, pipeline, repository and worker."""
    engine = build_engine(settings)
    diarizer = PyannoteDiarizer(
        token=settings.huggingface_token, model_name=settings.diarizer_model
    )
    post_processor = build_post_processor(settings)
    pipeline = Pipeline(
        engine=engine,
        diarizer=diarizer,
        post_processor=post_processor,
        settings=settings,
    )
    repository = JobRepository()
    worker = Worker(repository, pipeline, workers=settings.job.workers)
    if start_worker:
        worker.start()
    return Components(
        settings=settings,
        engine=engine,
        diarizer=diarizer,
        post_processor=post_processor,
        pipeline=pipeline,
        repository=repository,
        worker=worker,
    )


class ExportRequest(BaseModel):
    job_id: str
    formats: list[str] = Field(default_factory=lambda: exporters.supported_formats())


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(name).name).strip(" .")
    return cleaned or "media"


def _media_root(settings: Settings) -> Path:
    return Path(settings.media.dir).expanduser().resolve()


def _confined_media_path(settings: Settings, raw: str) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = _media_root(settings) / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"media_path not found: {raw}") from exc
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail="media_path must be a file")
    if not resolved.is_relative_to(_media_root(settings)):
        raise HTTPException(
            status_code=400, detail="media_path must live inside the configured media directory"
        )
    return resolved


def create_app(
    settings: Settings | None = None,
    components: Components | None = None,
    start_worker: bool = True,
) -> FastAPI:
    settings = settings or Settings()
    components = components or build_components(settings, start_worker=start_worker)
    media_dir = settings.ensure_media_dir()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            components.worker.stop()

    app = FastAPI(
        title="Antigravity Transcriptor Studio",
        version=VERSION,
        lifespan=lifespan,
    )
    app.state.components = components

    def require_job(job_id: str) -> Job:
        job = components.repository.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
        return job

    def require_transcript(job_id: str) -> tuple[Job, Any]:
        job = require_job(job_id)
        if job.status is not JobState.READY or job.transcript is None:
            raise HTTPException(
                status_code=409,
                detail=f"job is not ready (status={job.status.value})",
            )
        return job, job.transcript

    # ------------------------------------------------------------------ health
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "version": VERSION,
            "engine": settings.app.engine,
            "worker_running": components.worker.running,
            "ffmpeg": ffmpeg_available(),
        }

    # ------------------------------------------------------------------ models
    @app.get("/api/models")
    def models() -> dict[str, Any]:
        return {
            "engines": list(ENGINE_CHOICES),
            "engine": settings.app.engine,
            "model_sizes": list(MODEL_SIZES),
            "model": settings.model.size,
            "device": settings.device,
            "compute_type": settings.resolved_compute_type,
            "post_providers": list(POST_PROVIDERS),
            "post_provider": settings.post.provider,
            "diarization": {
                "enabled": settings.diarization_enabled,
                "model": settings.diarizer_model,
            },
            "formats": [
                {"key": spec.key, "extension": spec.extension, "mime": spec.mime}
                for spec in exporters.FORMATS.values()
            ],
            "max_upload_mb": settings.max_upload_mb,
        }

    @app.get("/api/formats")
    def formats() -> dict[str, Any]:
        return {
            "formats": [
                {"key": spec.key, "extension": spec.extension, "mime": spec.mime}
                for spec in exporters.FORMATS.values()
            ]
        }

    # -------------------------------------------------------------------- jobs
    @app.post("/api/jobs", status_code=202)
    async def create_job(
        file: UploadFile | None = File(default=None),
        media_path: str | None = Form(default=None),
        language: str | None = Form(default=None),
    ) -> dict[str, Any]:
        if file is None and not media_path:
            raise HTTPException(status_code=400, detail="provide a file upload or media_path")
        if file is not None:
            original = _safe_filename(file.filename or "upload")
            suffix = Path(original).suffix
            destination = media_dir / f"{uuid.uuid4().hex}{suffix}"
            max_bytes = settings.max_upload_mb * 1024 * 1024  # MB -> bytes
            size = 0
            try:
                with destination.open("wb") as handle:
                    while True:
                        chunk = await file.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > max_bytes:
                            raise HTTPException(
                                status_code=413,
                                detail=f"upload exceeds {settings.max_upload_mb} MB",
                            )
                        handle.write(chunk)
            except HTTPException:
                destination.unlink(missing_ok=True)
                raise
            finally:
                await file.close()
            if size == 0:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="uploaded file is empty")
            job = components.repository.create(
                file_name=original,
                media_path=destination,
                uploaded=True,
                language=language or None,
            )
        else:
            resolved = _confined_media_path(settings, media_path or "")
            job = components.repository.create(
                file_name=resolved.name,
                media_path=resolved,
                uploaded=False,
                language=language or None,
            )
        components.worker.submit(job)
        return job.to_dict()

    @app.get("/api/jobs")
    def list_jobs() -> dict[str, Any]:
        return {"jobs": [job.to_dict() for job in components.repository.list()]}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        return require_job(job_id).to_dict()

    @app.delete("/api/jobs/{job_id}")
    def delete_job(job_id: str) -> dict[str, Any]:
        job = require_job(job_id)
        if not job.is_terminal:
            job.cancel()
        if job.uploaded and job.media_path is not None:
            Path(job.media_path).unlink(missing_ok=True)
        components.repository.delete(job_id)
        return {"deleted": job_id}

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict[str, Any]:
        job = require_job(job_id)
        if not job.cancel():
            raise HTTPException(
                status_code=409,
                detail=f"job already finished (status={job.status.value})",
            )
        return {"id": job.id, "status": job.status.value, "cancelling": True}

    # --------------------------------------------------------------------- SSE
    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str, request: Request) -> StreamingResponse:
        if not settings.sse.enabled:
            raise HTTPException(status_code=404, detail="SSE is disabled")
        require_job(job_id)

        async def stream():
            while True:
                if await request.is_disconnected():
                    return
                job = components.repository.get(job_id)
                if job is None:
                    yield "event: error\ndata: {\"detail\": \"job removed\"}\n\n"
                    return
                payload = {
                    "id": job.id,
                    "status": job.status.value,
                    "progress": job.progress,
                    "message": job.message,
                    "error": job.error,
                }
                yield f"data: {json.dumps(payload)}\n\n"
                if job.is_terminal:
                    return
                await asyncio.sleep(0.25)

        return StreamingResponse(stream(), media_type="text/event-stream")

    # ----------------------------------------------------------------- exports
    @app.get("/api/jobs/{job_id}/export/{fmt}")
    def export_job(job_id: str, fmt: str) -> Response:
        _job, transcript = require_transcript(job_id)
        try:
            spec = exporters.get_format(fmt)
        except KeyError as exc:
            raise HTTPException(status_code=415, detail=str(exc)) from exc
        content = spec.render(transcript)
        filename = exporters.filename_for(fmt, transcript.file_name or "transcript")
        return Response(
            content=content,
            media_type=spec.mime,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/export")
    def export_bundle(payload: ExportRequest) -> Response:
        _job, transcript = require_transcript(payload.job_id)
        formats = payload.formats or exporters.supported_formats()
        unknown = [fmt for fmt in formats if fmt not in exporters.FORMATS]
        if unknown:
            raise HTTPException(status_code=415, detail=f"unsupported formats: {unknown}")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for fmt in formats:
                filename = exporters.filename_for(fmt, transcript.file_name or "transcript")
                info = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                archive.writestr(info, exporters.render(fmt, transcript))
        stem = Path(transcript.file_name or "transcript").stem
        return Response(
            content=buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{stem}_transcripts.zip"'
            },
        )

    # --------------------------------------------------------------- frontend
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")

    return app


def main() -> None:  # pragma: no cover - launcher
    import uvicorn

    backend_dir = Path(__file__).resolve().parent.parent
    uvicorn.run(
        "core.app:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        app_dir=str(backend_dir),
        reload=False,
    )


app = create_app()
