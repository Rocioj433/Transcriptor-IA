"""Regression: a cancel reported mid-run must finalize CANCELLED, never READY."""

import time

from core.job import JobState
from core.queue import JobRepository
from core.worker import Worker
from tests.conftest import BlockingEngine, StubEngine, StubPostProcessor, fake_extract
from core.pipeline import Pipeline


def wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_reported_cancel_finalizes_cancelled_not_ready(settings, tmp_path):
    engine = BlockingEngine()
    pipeline = Pipeline(engine, settings=settings, audio_extractor=fake_extract)
    repository = JobRepository()
    worker = Worker(repository, pipeline, workers=1).start()
    media = tmp_path / "clip.mp3"
    media.write_bytes(b"x")
    job = repository.create("clip.mp3", media, uploaded=True)
    try:
        worker.submit(job)
        assert wait_until(engine.started.is_set)
        assert job.cancel() is True
        assert wait_until(lambda: job.is_terminal)
        assert job.status is JobState.CANCELLED
        assert job.progress == -1
        assert not media.exists()
    finally:
        worker.stop()


def test_victory_path_is_still_ready(settings, tmp_path):
    pipeline = Pipeline(StubEngine(), post_processor=StubPostProcessor(), settings=settings, audio_extractor=fake_extract)
    repository = JobRepository()
    worker = Worker(repository, pipeline, workers=1).start()
    media = tmp_path / "clip.mp3"
    media.write_bytes(b"x")
    job = repository.create("clip.mp3", media, uploaded=True)
    try:
        worker.submit(job)
        assert wait_until(lambda: job.is_terminal)
        assert job.status is JobState.READY
        assert job.transcript is not None
    finally:
        worker.stop()
