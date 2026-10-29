import io
import zipfile

import exporters
from core.job import JobState
from engines.schema import Segment, Transcript
from tests.conftest import make_transcript


def ready_job(components, transcript=None):
    job = components.repository.create("demo.mp3")
    job.status = JobState.READY
    job.progress = 100
    job.transcript = transcript or make_transcript()
    return job


def test_export_srt_headers(client, components):
    job = ready_job(components)
    response = client.get(f"/api/jobs/{job.id}/export/srt")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-subrip")
    assert 'filename="demo.srt"' in response.headers["content-disposition"]
    assert b"00:00:00,500 --> 00:00:05,000" in response.content


def test_export_docx_mime(client, components):
    job = ready_job(components)
    response = client.get(f"/api/jobs/{job.id}/export/docx")
    assert response.status_code == 200
    assert response.content.startswith(b"PK")
    assert "wordprocessingml" in response.headers["content-type"]


def test_unsupported_format_is_415(client, components):
    job = ready_job(components)
    assert client.get(f"/api/jobs/{job.id}/export/ass").status_code == 415


def test_export_before_ready_is_409(client, components):
    job = components.repository.create("pending.mp3")
    assert client.get(f"/api/jobs/{job.id}/export/txt").status_code == 409
    response = client.post("/api/export", json={"job_id": job.id, "formats": ["txt"]})
    assert response.status_code == 409


def test_export_unknown_job_is_404(client):
    assert client.get("/api/jobs/nope/export/txt").status_code == 404


def test_zip_bundle_contains_every_format(client, components):
    job = ready_job(components)
    response = client.post("/api/export", json={"job_id": job.id})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert 'filename="demo_transcripts.zip"' in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {
            f"demo.{fmt}" for fmt in exporters.supported_formats()
        }
        assert archive.read("demo.srt") == exporters.render("srt", job.transcript)


def test_zip_bundle_respects_subset_and_rejects_unknown(client, components):
    job = ready_job(components)
    response = client.post("/api/export", json={"job_id": job.id, "formats": ["txt", "md"]})
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"demo.txt", "demo.md"}
    bad = client.post("/api/export", json={"job_id": job.id, "formats": ["ass"]})
    assert bad.status_code == 415


def test_export_uses_empty_transcript_without_crashing(client, components):
    empty = Transcript(file_name="empty.mp3", duration=0.0, language="unknown", model_used="m")
    job = ready_job(components, transcript=empty)
    assert client.get(f"/api/jobs/{job.id}/export/txt").content == b""
    assert client.get(f"/api/jobs/{job.id}/export/vtt").content.startswith(b"WEBVTT")


def test_export_filename_sanitizes_media_name(client, components):
    transcript = make_transcript()
    transcript.file_name = "mi audio (final).mp3"
    job = ready_job(components, transcript=transcript)
    response = client.get(f"/api/jobs/{job.id}/export/txt")
    assert "mi audio (final).txt" in response.headers["content-disposition"]
