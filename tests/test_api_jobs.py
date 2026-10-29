import time
from contextlib import contextmanager

from fastapi.testclient import TestClient

from core.app import create_app
from core.config import JobSettings, MediaSettings, Settings, SseSettings
from tests.conftest import BlockingEngine, build_test_components, wait_for_job


@contextmanager
def api(settings: Settings, **kwargs):
    components = build_test_components(settings, **kwargs)
    client = TestClient(create_app(settings=settings, components=components))
    try:
        yield client, components
    finally:
        client.close()
        components.worker.stop()


def upload(client, name="demo.mp3", content=b"fake-audio", data=None):
    return client.post(
        "/api/jobs",
        files={"file": (name, content, "audio/mpeg")},
        data=data or {},
    )


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["engine"] == "faster-whisper"
    assert payload["worker_running"] is True


def test_models_and_formats(client):
    payload = client.get("/api/models").json()
    assert payload["model"] == "large-v3-turbo"
    assert "faster-whisper" in payload["engines"]
    assert payload["diarization"]["enabled"] is False
    assert {fmt["key"] for fmt in payload["formats"]} == {
        "txt",
        "srt",
        "vtt",
        "docx",
        "pdf",
        "json",
        "csv",
        "md",
    }
    assert client.get("/api/formats").status_code == 200


def test_upload_job_reaches_ready(client, components):
    response = upload(client, data={"language": "es"})
    assert response.status_code == 202
    job_id = response.json()["id"]
    payload = wait_for_job(client, job_id)
    assert payload["status"] == "ready"
    assert payload["progress"] == 100
    assert payload["transcript"]["speakers"] == ["A", "B"]
    assert components.engine.calls[0][1] == "es"
    listed = client.get("/api/jobs").json()["jobs"]
    assert listed[0]["id"] == job_id


def test_missing_input_is_rejected(client):
    assert client.post("/api/jobs").status_code == 400


def test_empty_upload_is_rejected(client):
    response = client.post("/api/jobs", files={"file": ("empty.mp3", b"", "audio/mpeg")})
    assert response.status_code == 400


def test_unknown_job_and_cancel_are_404(client):
    assert client.get("/api/jobs/nope").status_code == 404
    assert client.post("/api/jobs/nope/cancel").status_code == 404
    assert client.delete("/api/jobs/nope").status_code == 404


def test_cancel_finished_job_is_409(client):
    job_id = upload(client).json()["id"]
    wait_for_job(client, job_id)
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 409


def test_delete_job_removes_file(client, components, settings):
    job_id = upload(client).json()["id"]
    wait_for_job(client, job_id)
    job = components.repository.require(job_id)
    media = job.media_path
    assert media.exists()
    assert client.delete(f"/api/jobs/{job_id}").json() == {"deleted": job_id}
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    assert not media.exists()


def test_upload_limit_returns_413(tmp_path):
    settings = Settings(
        _env_file=None,
        media=MediaSettings(dir=tmp_path / "media"),
        job=JobSettings(workers=1),
        max_upload_mb=1,
    )
    with api(settings) as (client, _components):
        response = upload(client, content=b"x" * (1024 * 1024 + 10))
        assert response.status_code == 413


def test_media_path_must_be_inside_media_dir(client, settings, tmp_path):
    settings.ensure_media_dir()
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"x")
    response = client.post("/api/jobs", data={"media_path": str(outside)})
    assert response.status_code == 400
    missing = client.post("/api/jobs", data={"media_path": str(tmp_path / "nope.mp3")})
    assert missing.status_code == 404


def test_media_path_mode_accepts_confined_file(client, settings):
    media_dir = settings.ensure_media_dir()
    inside = media_dir / "in-house.mp3"
    inside.write_bytes(b"x")
    response = client.post("/api/jobs", data={"media_path": str(inside)})
    assert response.status_code == 202
    payload = wait_for_job(client, response.json()["id"])
    assert payload["status"] == "ready"
    assert payload["file_name"] == "in-house.mp3"


def test_cancel_running_job_reaches_cancelled(settings):
    engine = BlockingEngine()
    with api(settings, engine=engine) as (client, components):
        job_id = upload(client).json()["id"]
        deadline = time.monotonic() + 5
        while not engine.started.is_set() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert engine.started.is_set(), "worker never started the blocking engine"
        response = client.post(f"/api/jobs/{job_id}/cancel")
        assert response.status_code == 200
        payload = wait_for_job(client, job_id)
        assert payload["status"] == "cancelled"
        assert payload["progress"] == -1
        job = components.repository.require(job_id)
        assert job.media_path is not None and not job.media_path.exists()


def test_sse_stream_reports_terminal_state(client):
    job_id = upload(client).json()["id"]
    wait_for_job(client, job_id)
    with client.stream("GET", f"/api/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())
    assert '"status": "ready"' in body


def test_sse_disabled_returns_404(tmp_path):
    settings = Settings(
        _env_file=None,
        media=MediaSettings(dir=tmp_path / "media"),
        job=JobSettings(workers=1),
        sse=SseSettings(enabled=False),
    )
    with api(settings) as (client, _components):
        job_id = upload(client).json()["id"]
        wait_for_job(client, job_id)
        assert client.get(f"/api/jobs/{job_id}/events").status_code == 404
