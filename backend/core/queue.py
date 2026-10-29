"""In-memory job model and repository (single-process, local-first)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from core.job import JobState, PROGRESS
from engines.schema import Transcript


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Job:
    id: str
    file_name: str
    media_path: Path | None = None
    uploaded: bool = False
    language: str | None = None
    status: JobState = JobState.QUEUED
    progress: int = PROGRESS[JobState.QUEUED]
    message: str | None = None
    error: str | None = None
    transcript: Transcript | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    @property
    def is_terminal(self) -> bool:
        return self.status in (JobState.READY, JobState.ERROR, JobState.CANCELLED)

    def touch(self) -> None:
        self.updated_at = _now()

    def cancel(self) -> bool:
        """Signal cancellation. Returns False when the job already finished."""
        if self.is_terminal:
            return False
        self.cancel_event.set()
        return True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "file_name": self.file_name,
            "status": self.status.value,
            "progress": self.progress,
            "language": self.language,
            "message": self.message,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "transcript": self.transcript.to_dict() if self.transcript else None,
        }


class JobRepository:
    """Thread-safe in-memory repository keyed by job id."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}

    def create(
        self,
        file_name: str,
        media_path: Path | None = None,
        uploaded: bool = False,
        language: str | None = None,
    ) -> Job:
        job = Job(
            id=uuid.uuid4().hex,
            file_name=file_name,
            media_path=Path(media_path) if media_path else None,
            uploaded=uploaded,
            language=language,
        )
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def require(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def update(self, job: Job) -> Job:
        job.touch()
        with self._lock:
            self._jobs[job.id] = job
        return job

    def list(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)

    def delete(self, job_id: str) -> bool:
        with self._lock:
            return self._jobs.pop(job_id, None) is not None

    def __iter__(self) -> Iterator[Job]:  # pragma: no cover - convenience
        return iter(self.list())

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()
