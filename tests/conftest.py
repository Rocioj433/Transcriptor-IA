"""Shared fixtures: stubs, synthetic WAV files and an injected FastAPI client."""

from __future__ import annotations

import copy
import math
import threading
import time
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.app import Components, create_app
from core.config import JobSettings, MediaSettings, Settings, SseSettings
from core.errors import CancelledError
from core.pipeline import Pipeline
from core.queue import JobRepository
from core.worker import Worker
from engines.schema import Segment, Transcript, Word

GOLDEN_DIR = Path(__file__).parent / "golden"


def make_transcript() -> Transcript:
    return Transcript(
        file_name="demo.mp3",
        duration=65.25,
        language="es",
        model_used="large-v3-turbo",
        segments=[
            Segment(
                id=0,
                start=0.5,
                end=5.0,
                text="Hola, ¿cómo estás?",
                speaker="A",
                confidence=0.98,
                words=[
                    Word(0, "Hola", 0.5, 0.9),
                    Word(1, "cómo", 1.0, 1.4),
                    Word(2, "estás", 1.5, 2.0),
                ],
            ),
            Segment(
                id=1,
                start=5.0,
                end=65.25,
                text="Muy bien, gracias.",
                speaker="B",
                confidence=0.91,
                words=[],
            ),
            Segment(
                id=2,
                start=66.0,
                end=70.0,
                text="Sin hablante asignado.",
                speaker=None,
                confidence=0.5,
                words=[],
            ),
        ],
    )


class StubEngine:
    name = "stub"

    def __init__(self, transcript: Transcript | None = None, delay: float = 0.0) -> None:
        self.transcript = transcript or make_transcript()
        self.delay = delay
        self.calls: list[tuple[Path, str | None]] = []

    def transcribe(self, path, language=None, cancel=None):
        self.calls.append((Path(path), language))
        deadline = time.monotonic() + self.delay
        while time.monotonic() < deadline:
            if cancel is not None and cancel.is_set():
                raise CancelledError("cancelled during stub transcription")
            time.sleep(0.02)
        if cancel is not None and cancel.is_set():
            raise CancelledError("cancelled during stub transcription")
        return copy.deepcopy(self.transcript)


class BlockingEngine:
    """Blocks until cancelled, then raises — deterministic cancel test."""

    name = "blocking"

    def __init__(self) -> None:
        self.started = threading.Event()

    def transcribe(self, path, language=None, cancel=None):
        self.started.set()
        assert cancel is not None
        cancel.wait(timeout=10)
        raise CancelledError("cancelled while transcribing")


class StubDiarizer:
    name = "stub-diarizer"

    def __init__(self) -> None:
        from core.diarizer.base import SpeakerSpan

        self.spans = [
            SpeakerSpan(0.0, 6.0, "A"),
            SpeakerSpan(6.0, 65.5, "B"),
        ]

    def diarize(self, path, cancel=None):
        return list(self.spans)


class UnavailableDiarizer:
    name = "unavailable"

    def diarize(self, path, cancel=None):
        from core.errors import DiarizationUnavailable

        raise DiarizationUnavailable("HUGGINGFACE_TOKEN is not configured")


class StubPostProcessor:
    name = "stub-post"

    def __init__(self, transform=None, raises: Exception | None = None) -> None:
        self.transform = transform or (lambda text: text.upper())
        self.raises = raises

    def cleanup(self, transcript: Transcript) -> Transcript:
        if self.raises:
            raise self.raises
        cleaned = copy.deepcopy(transcript)
        cleaned.raw_segments = copy.deepcopy(transcript.segments)
        for segment in cleaned.segments:
            segment.text = self.transform(segment.text)
        return cleaned


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        media=MediaSettings(dir=tmp_path / "media"),
        huggingface_token="",
        job=JobSettings(workers=1),
        sse=SseSettings(enabled=True),
    )


@pytest.fixture
def wav_file(tmp_path: Path) -> Path:
    """1 second of 16 kHz mono PCM silence."""
    path = tmp_path / "sample.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        frames = bytearray()
        for index in range(16000):
            value = int(3000 * math.sin(2 * math.pi * 440 * index / 16000))
            frames += value.to_bytes(2, "little", signed=True)
        handle.writeframes(bytes(frames))
    return path


def fake_extract(source, workspace, cancel=None):
    """Audio extractor stub: skip ffmpeg and hand the source path through."""
    if cancel is not None and cancel.is_set():
        raise CancelledError("cancelled during extraction")
    return Path(source)


def build_test_components(
    settings: Settings,
    engine=None,
    diarizer=None,
    post_processor=None,
    start_worker: bool = True,
) -> Components:
    engine = engine or StubEngine()
    pipeline = Pipeline(
        engine=engine,
        diarizer=diarizer,
        post_processor=post_processor,
        settings=settings,
        audio_extractor=fake_extract,
        duration_probe=lambda _path: 12.0,
    )
    repository = JobRepository()
    worker = Worker(repository, pipeline, workers=1)
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


@pytest.fixture
def components(settings: Settings) -> Components:
    built = build_test_components(settings)
    yield built
    built.worker.stop()


@pytest.fixture
def client(settings: Settings, components: Components) -> TestClient:
    test_client = TestClient(create_app(settings=settings, components=components))
    yield test_client
    test_client.close()


def wait_for_job(client: TestClient, job_id: str, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    payload: dict = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] in ("ready", "error", "cancelled"):
            return payload
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s: {payload}")


def pytest_addoption(parser):
    parser.addoption(
        "--update-goldens",
        action="store_true",
        default=False,
        help="rewrite golden exporter files instead of asserting",
    )


@pytest.fixture
def assert_golden(request):
    def _assert(name: str, data: bytes) -> None:
        path = GOLDEN_DIR / name
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        if request.config.getoption("--update-goldens") or not path.exists():
            path.write_bytes(data)
        assert data == path.read_bytes(), f"golden mismatch for {name}"

    return _assert


@pytest.fixture
def no_diarizer():
    return None
