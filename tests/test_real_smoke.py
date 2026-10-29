"""Optional smoke tests against real models/audio (deselected by default).

Run with:
    $env:SMOKE_AUDIO="C:\\ruta\\voz.wav"
    pytest -m slow -q
"""

import os
import threading

import pytest

from core.pipeline import Pipeline
from core.queue import JobRepository
from engines.faster_whisper_engine import FasterWhisperEngine

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def smoke_audio():
    value = os.environ.get("SMOKE_AUDIO")
    if not value or not os.path.exists(value):
        pytest.skip("set SMOKE_AUDIO to a real speech file to run the slow smoke test")
    return value


def test_real_faster_whisper_transcribes_speech(smoke_audio):
    pytest.importorskip("faster_whisper")
    engine = FasterWhisperEngine(model_size=os.environ.get("SMOKE_MODEL", "tiny"), device="cpu", compute_type="int8")
    transcript = engine.transcribe(smoke_audio, cancel=threading.Event())
    assert transcript.segments
    assert transcript.text.strip()
    assert transcript.duration > 0
    assert transcript.model_used


def test_real_pipeline_without_diarization(smoke_audio):
    pytest.importorskip("faster_whisper")
    engine = FasterWhisperEngine(model_size=os.environ.get("SMOKE_MODEL", "tiny"), device="cpu", compute_type="int8")
    pipeline = Pipeline(engine=engine)
    repository = JobRepository()
    job = repository.create("smoke.wav", smoke_audio)
    transcript = pipeline.run(job)
    assert job.progress == 100
    assert transcript.segments
    assert transcript.raw_segments is None
