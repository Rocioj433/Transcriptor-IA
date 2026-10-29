import pytest

from core.errors import CancelledError
from core.job import JobState
from core.pipeline import Pipeline
from core.queue import JobRepository
from tests.conftest import (
    StubDiarizer,
    StubEngine,
    StubPostProcessor,
    UnavailableDiarizer,
    fake_extract,
    make_transcript,
)


def build_pipeline(settings, job, engine=None, diarizer=None, post=None, transcript=None):
    pipeline = Pipeline(
        engine=engine or StubEngine(transcript=transcript),
        diarizer=diarizer,
        post_processor=post,
        settings=settings,
        audio_extractor=fake_extract,
        duration_probe=lambda _path: 12.0,
    )
    return pipeline, job


def make_job(repo: JobRepository, tmp_path):
    return repo.create("demo.mp3", tmp_path / "demo.mp3", uploaded=True)


def test_full_pipeline_reaches_ready(settings, tmp_path):
    repo = JobRepository()
    job = make_job(repo, tmp_path)
    pipeline, job = build_pipeline(
        settings, job, diarizer=StubDiarizer(), post=StubPostProcessor()
    )
    transcript = pipeline.run(job)
    assert job.status is JobState.READY
    assert job.progress == 100
    assert job.transcript is transcript
    assert transcript.speakers == ["A", "B"]
    assert transcript.segments[0].text == "HOLA, ¿CÓMO ESTÁS?"
    assert transcript.raw_segments[0].text == "Hola, ¿cómo estás?"
    assert transcript.duration == 65.25
    assert job.message is None


def test_pipeline_without_diarizer_warns_but_finishes(settings, tmp_path):
    repo = JobRepository()
    job = make_job(repo, tmp_path)
    pipeline, job = build_pipeline(settings, job)
    transcript = pipeline.run(job)
    assert job.status is JobState.READY
    assert any("no diarizer configured" in warning for warning in transcript.warnings)
    assert transcript.speakers == ["A", "B"]


def test_pipeline_diarization_unavailable_falls_back(settings, tmp_path):
    repo = JobRepository()
    job = make_job(repo, tmp_path)
    pipeline, job = build_pipeline(settings, job, diarizer=UnavailableDiarizer())
    transcript = pipeline.run(job)
    assert job.status is JobState.READY
    assert any("diarization-unavailable" in warning for warning in transcript.warnings)
    assert "HUGGINGFACE_TOKEN" in transcript.warnings[0]
    assert job.message is not None


def test_pipeline_post_failure_is_non_blocking(settings, tmp_path):
    repo = JobRepository()
    job = make_job(repo, tmp_path)
    post = StubPostProcessor(raises=RuntimeError("llm down"))
    pipeline, job = build_pipeline(settings, job, diarizer=StubDiarizer(), post=post)
    transcript = pipeline.run(job)
    assert job.status is JobState.READY
    assert any("post-process-unavailable" in warning for warning in transcript.warnings)
    assert transcript.segments[0].text == "Hola, ¿cómo estás?"


def test_pipeline_cancel_between_stages(settings, tmp_path):
    repo = JobRepository()
    job = make_job(repo, tmp_path)

    class CancellingEngine(StubEngine):
        def transcribe(self, path, language=None, cancel=None):
            cancel.set()
            return make_transcript()

    pipeline, job = build_pipeline(settings, job, engine=CancellingEngine())
    with pytest.raises(CancelledError):
        pipeline.run(job)
    assert job.status is not JobState.READY


def test_pipeline_probes_duration_when_engine_reports_zero(settings, tmp_path):
    repo = JobRepository()
    job = make_job(repo, tmp_path)
    transcript = make_transcript()
    transcript.duration = 0.0
    pipeline, job = build_pipeline(settings, job, transcript=transcript)
    result = pipeline.run(job)
    assert result.duration == 12.0


def test_pipeline_uses_job_file_name(settings, tmp_path):
    repo = JobRepository()
    job = repo.create("subida.wav", tmp_path / "subida.wav", uploaded=True)
    pipeline, job = build_pipeline(settings, job)
    result = pipeline.run(job)
    assert result.file_name == "subida.wav"
