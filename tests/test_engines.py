import threading
from types import SimpleNamespace

import pytest

from core.config import Settings
from core.errors import CancelledError
from engines.base import available_engines, build_engine, get_engine, register_engine
from engines.cloud import CloudTranscribeEngine
from engines.faster_whisper_engine import FasterWhisperEngine
from engines.openai_whisper import OpenAIWhisperEngine
from engines.schema import Word


class FakeWord:
    def __init__(self, index, word, start, end):
        self.index, self.word, self.start, self.end = index, word, start, end


class FakeSegment:
    def __init__(self, start, end, text, words=None, avg_logprob=-0.1):
        self.start, self.end, self.text = start, end, text
        self.words = words or []
        self.avg_logprob = avg_logprob


class FakeWhisperModel:
    def __init__(self, segments):
        self.segments = segments
        self.kwargs = None

    def transcribe(self, path, **kwargs):
        self.kwargs = kwargs
        return iter(self.segments), SimpleNamespace(duration=12.5, language="es")


def test_faster_whisper_builds_common_schema():
    model = FakeWhisperModel(
        [FakeSegment(0.0, 1.0, "hola", [FakeWord(0, "hola", 0.0, 1.0)])]
    )
    engine = FasterWhisperEngine(model=model)
    transcript = engine.transcribe("audio.wav")
    assert transcript.model_used == "large-v3-turbo"
    assert transcript.language == "es"
    assert transcript.duration == 12.5
    assert transcript.segments[0].text == "hola"
    assert transcript.segments[0].words == [Word(0, "hola", 0.0, 1.0)]
    assert 0 < transcript.segments[0].confidence <= 1
    assert model.kwargs["vad_filter"] is True
    assert model.kwargs["word_timestamps"] is True


def test_faster_whisper_forwards_language_override():
    model = FakeWhisperModel([FakeSegment(0.0, 1.0, "hi")])
    FasterWhisperEngine(model=model).transcribe("a.wav", language="en")
    assert model.kwargs["language"] == "en"


def test_faster_whisper_cancel_raises_between_segments():
    cancel = threading.Event()

    def generate():
        yield FakeSegment(0.0, 1.0, "one")
        cancel.set()
        yield FakeSegment(1.0, 2.0, "two")

    model = FakeWhisperModel(generate())
    with pytest.raises(CancelledError):
        FasterWhisperEngine(model=model).transcribe("a.wav", cancel=cancel)


def test_openai_whisper_engine_parses_result():
    class FakeModel:
        def transcribe(self, path, **kwargs):
            return {
                "language": "en",
                "segments": [
                    {
                        "start": 0.0,
                        "end": 1.0,
                        "text": " hello ",
                        "no_speech_prob": 0.1,
                        "words": [{"id": 0, "word": "hello", "start": 0.0, "end": 1.0}],
                    }
                ],
            }

    transcript = OpenAIWhisperEngine(model=FakeModel()).transcribe("a.wav")
    assert transcript.language == "en"
    assert transcript.model_used == "openai-whisper:large-v3-turbo"
    assert transcript.segments[0].text == "hello"
    assert transcript.segments[0].confidence == pytest.approx(0.9)


def test_cloud_engine_parses_segments_and_words(tmp_path):
    captured = {}

    class FakeTranscriptions:
        def create(self, file, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                model_dump=lambda: {
                    "text": "hola mundo",
                    "language": "es",
                    "duration": 3.0,
                    "segments": [{"start": 0.0, "end": 2.0, "text": "hola mundo"}],
                    "words": [
                        {"id": 0, "word": "hola", "start": 0.0, "end": 1.0},
                        {"id": 1, "word": "mundo", "start": 1.0, "end": 2.0},
                    ],
                }
            )

    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=FakeTranscriptions()))
    engine = CloudTranscribeEngine(api_key="sk-x", client=client)
    path = tmp_path / "a.wav"
    path.write_bytes(b"audio")
    transcript = engine.transcribe(path, language="es")
    assert transcript.model_used == "gpt-4o-transcribe"
    assert transcript.segments[0].words[0].word == "hola"
    assert captured["response_format"] == "verbose_json"


def test_cloud_engine_requires_api_key_without_client():
    with pytest.raises(ValueError):
        CloudTranscribeEngine(api_key="")


def test_registry_roundtrip_and_unknown():
    register_engine("dummy-engine", FasterWhisperEngine)
    assert get_engine("dummy-engine") is FasterWhisperEngine
    assert "dummy-engine" in available_engines()
    with pytest.raises(KeyError):
        get_engine("nope")


def test_build_engine_local_defaults():
    engine = build_engine(Settings(_env_file=None))
    assert isinstance(engine, FasterWhisperEngine)
    assert engine.model_size == "large-v3-turbo"
    assert engine.compute_type == "int8"


def test_build_engine_cloud_requires_key():
    settings = Settings(_env_file=None, app={"engine": "cloud-transcribe"})
    with pytest.raises(KeyError):
        build_engine(settings)


def test_build_engine_cloud_with_key():
    settings = Settings(
        _env_file=None,
        app={"engine": "cloud-transcribe"},
        cloud={"api_key": "sk-test"},
    )
    engine = build_engine(settings)
    assert isinstance(engine, CloudTranscribeEngine)
