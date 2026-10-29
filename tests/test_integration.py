import time

from fastapi.testclient import TestClient

from core.app import create_app
from core.diarizer.pyannote import PyannoteDiarizer
from tests.conftest import (
    StubDiarizer,
    StubEngine,
    StubPostProcessor,
    build_test_components,
    make_transcript,
    wait_for_job,
)


def make_api(settings, **kwargs):
    components = build_test_components(settings, **kwargs)
    return TestClient(create_app(settings=settings, components=components)), components


def test_end_to_end_upload_diarize_post_and_export(settings, wav_file):
    client, components = make_api(
        settings, diarizer=StubDiarizer(), post_processor=StubPostProcessor()
    )
    try:
        with wav_file.open("rb") as handle:
            response = client.post(
                "/api/jobs",
                files={"file": ("entrevista.wav", handle, "audio/wav")},
            )
        assert response.status_code == 202
        payload = wait_for_job(client, response.json()["id"])

        assert payload["status"] == "ready"
        assert payload["transcript"]["speakers"] == ["A", "B"]
        assert payload["transcript"]["segments"][0]["text"] == "HOLA, ¿CÓMO ESTÁS?"
        assert payload["transcript"]["raw_segments"][0]["text"] == "Hola, ¿cómo estás?"
        assert payload["transcript"]["model_used"] == "large-v3-turbo"

        exported = client.get(f"/api/jobs/{payload['id']}/export/srt")
        assert exported.status_code == 200
        assert b"A: HOLA" in exported.content

        bundle = client.post("/api/export", json={"job_id": payload["id"], "formats": ["txt", "docx"]})
        assert bundle.status_code == 200
    finally:
        client.close()
        components.worker.stop()


def test_real_pyannote_without_token_falls_back(settings):
    transcript = make_transcript()
    for segment in transcript.segments:
        segment.speaker = None
    client, components = make_api(
        settings,
        engine=StubEngine(transcript=transcript),
        diarizer=PyannoteDiarizer(token=""),
    )
    try:
        response = client.post(
            "/api/jobs", files={"file": ("a.mp3", b"data", "audio/mpeg")}
        )
        payload = wait_for_job(client, response.json()["id"])
        assert payload["status"] == "ready"
        assert "diarization-unavailable" in payload["message"]
        assert payload["transcript"]["speakers"] == []
    finally:
        client.close()
        components.worker.stop()


def test_engine_failure_marks_job_error_and_cleans_upload(settings):
    class ExplodingEngine:
        name = "boom"

        def transcribe(self, path, language=None, cancel=None):
            raise RuntimeError("model exploded")

    client, components = make_api(settings, engine=ExplodingEngine())
    try:
        response = client.post(
            "/api/jobs", files={"file": ("a.mp3", b"data", "audio/mpeg")}
        )
        job_id = response.json()["id"]
        payload = wait_for_job(client, job_id)
        assert payload["status"] == "error"
        assert payload["progress"] == -1
        assert "RuntimeError: model exploded" in payload["error"]
        job = components.repository.require(job_id)
        assert job.media_path is not None and not job.media_path.exists()
    finally:
        client.close()
        components.worker.stop()


def test_synthetic_wav_upload_completes(settings, wav_file):
    """Uses ffmpeg when available and the WAV copy fallback otherwise."""
    client, components = make_api(settings, diarizer=StubDiarizer())
    try:
        with wav_file.open("rb") as handle:
            response = client.post(
                "/api/jobs", files={"file": ("sample.wav", handle, "audio/wav")}
            )
        payload = wait_for_job(client, response.json()["id"])
        assert payload["status"] == "ready"
    finally:
        client.close()
        components.worker.stop()
