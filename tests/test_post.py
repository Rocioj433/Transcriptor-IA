import json
from types import SimpleNamespace

import pytest

from core.config import Settings
from core.post.base import apply_cleanup, build_post_processor, build_prompt
from core.post.ollama import OllamaPostProcessor
from core.post.openai import OpenAIPostProcessor
from tests.conftest import make_transcript


def test_apply_cleanup_replaces_text_and_keeps_raw():
    transcript = make_transcript()
    response = json.dumps(
        {"segments": [{"id": 0, "text": "Hola, ¿cómo estás?"}, {"id": 1, "text": "Muy bien."}]}
    )
    cleaned = apply_cleanup(transcript, response)
    assert cleaned.segments[0].text == "Hola, ¿cómo estás?"
    assert cleaned.segments[1].text == "Muy bien."
    assert cleaned.segments[0].speaker == "A"
    assert cleaned.raw_segments is not None
    assert cleaned.raw_segments[1].text == "Muy bien, gracias."
    assert transcript.segments[1].text == "Muy bien, gracias."


def test_apply_cleanup_accepts_fenced_json():
    response = '```json\n{"segments": [{"id": 0, "text": "ok"}]}\n```'
    cleaned = apply_cleanup(make_transcript(), response)
    assert cleaned.segments[0].text == "ok"


def test_apply_cleanup_rejects_invalid_payload():
    with pytest.raises((ValueError, json.JSONDecodeError)):
        apply_cleanup(make_transcript(), "not json")


def test_build_prompt_includes_ids():
    prompt = build_prompt(make_transcript())
    assert '"id": 0' in prompt
    assert "Return ONLY JSON" in prompt


def test_ollama_post_processor_uses_injected_client():
    captured = {}

    def fake_client(prompt: str) -> str:
        captured["prompt"] = prompt
        return '{"segments": [{"id": 0, "text": "limpio"}]}'

    processor = OllamaPostProcessor(client=fake_client)
    cleaned = processor.cleanup(make_transcript())
    assert cleaned.segments[0].text == "limpio"
    assert "Segments:" in captured["prompt"]


def test_ollama_request_failure_raises():
    def boom(prompt: str) -> str:
        raise RuntimeError("ollama request failed: connection refused")

    with pytest.raises(RuntimeError):
        OllamaPostProcessor(client=boom).cleanup(make_transcript())


def test_openai_post_processor_with_fake_client():
    class FakeCompletions:
        def create(self, **kwargs):
            message = SimpleNamespace(content='{"segments": [{"id": 1, "text": "hey"}]}')
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    processor = OpenAIPostProcessor(client=client)
    cleaned = processor.cleanup(make_transcript())
    assert cleaned.segments[1].text == "hey"


def test_openai_post_processor_requires_key():
    with pytest.raises(ValueError):
        OpenAIPostProcessor(api_key="")


def test_build_post_processor_variants():
    assert build_post_processor(Settings(_env_file=None)) is None
    ollama = build_post_processor(Settings(_env_file=None, post={"provider": "ollama"}))
    assert isinstance(ollama, OllamaPostProcessor)
    openai = build_post_processor(
        Settings(_env_file=None, post={"provider": "openai"}, cloud={"api_key": "sk-x"})
    )
    assert isinstance(openai, OpenAIPostProcessor)
