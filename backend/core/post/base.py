"""Post-processing SPI: optional LLM cleanup (punctuation / fillers)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from engines.schema import Segment, Transcript

PROMPT_TEMPLATE = (
    "You are a transcript editor. Clean the following transcription: fix punctuation and "
    "capitalization, remove filler words, but never change meaning, speakers or timing. "
    "Return ONLY JSON of the form "
    '{"segments": [{"id": <int>, "text": "<cleaned text>"}]} using the same ids.\n\n'
    "Segments:\n{segments}"
)


@runtime_checkable
class PostProcessor(Protocol):
    name: str

    def cleanup(self, transcript: Transcript) -> Transcript:  # pragma: no cover
        ...


def build_prompt(transcript: Transcript) -> str:
    payload = [{"id": segment.id, "text": segment.text} for segment in transcript.segments]
    return PROMPT_TEMPLATE.replace("{segments}", json.dumps(payload, ensure_ascii=False))


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def apply_cleanup(transcript: Transcript, response: str) -> Transcript:
    """Merge an LLM JSON response into a copy of ``transcript``."""
    data = json.loads(_strip_fences(response))
    entries = data.get("segments") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise ValueError("post-processor response has no segments list")
    cleaned_by_id: dict[int, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            cleaned_by_id[int(entry["id"])] = str(entry.get("text", "")).strip()
        except (KeyError, TypeError, ValueError):
            continue

    cleaned: list[Segment] = []
    for segment in transcript.segments:
        text = cleaned_by_id.get(segment.id, segment.text)
        cleaned.append(
            Segment(
                id=segment.id,
                start=segment.start,
                end=segment.end,
                text=text,
                speaker=segment.speaker,
                confidence=segment.confidence,
                words=list(segment.words),
            )
        )
    updated = copy.deepcopy(transcript)
    updated.raw_segments = transcript.raw_segments or copy.deepcopy(transcript.segments)
    updated.segments = cleaned
    return updated


def build_post_processor(settings: Any) -> PostProcessor | None:
    provider = settings.post.provider
    if provider == "none":
        return None
    if provider == "ollama":
        from core.post.ollama import OllamaPostProcessor

        return OllamaPostProcessor(
            base_url=settings.ollama.base_url,
            model=settings.ollama.model,
            timeout_s=settings.ollama.timeout_s,
        )
    if provider == "openai":
        from core.post.openai import OpenAIPostProcessor

        return OpenAIPostProcessor(
            api_key=settings.cloud.api_key, model=settings.ollama.model
        )
    raise ValueError(f"unknown post provider {provider!r}")
