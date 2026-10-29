"""Transcription engine SPI + registry.

Engines are registered by name so a provider can be swapped from settings
without touching the pipeline. Heavy dependencies are imported lazily inside
each implementation, which keeps the API importable without ML wheels.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from engines.schema import Transcript


@runtime_checkable
class TranscriptionEngine(Protocol):
    name: str

    def transcribe(
        self, path: Path, language: str | None = None, cancel: threading.Event | None = None
    ) -> Transcript:  # pragma: no cover - protocol definition
        ...


_ENGINES: dict[str, Any] = {}


def register_engine(name: str, engine_cls: Any) -> None:
    """Register an engine class/factory under ``name`` (idempotent overwrite)."""
    _ENGINES[name] = engine_cls


def get_engine(name: str) -> Any:
    """Return a registered engine factory, raising ``KeyError`` when unknown."""
    try:
        return _ENGINES[name]
    except KeyError as exc:
        raise KeyError(f"transcription engine {name!r} is not registered") from exc


def available_engines() -> list[str]:
    return sorted(_ENGINES)


def build_engine(settings: Any) -> TranscriptionEngine:
    """Instantiate the engine selected in ``settings``."""
    engine_name = settings.app.engine
    if engine_name == "faster-whisper":
        from engines.faster_whisper_engine import FasterWhisperEngine, register

        register()
        return get_engine(engine_name)(
            model_size=settings.model.size,
            device=settings.device,
            compute_type=settings.resolved_compute_type,
        )
    if engine_name == "openai-whisper":
        from engines.openai_whisper import OpenAIWhisperEngine, register

        register()
        return get_engine(engine_name)(
            model_size=settings.model.size, device=settings.device
        )
    if engine_name == "cloud-transcribe":
        from engines.cloud import CloudTranscribeEngine, register

        register()
        get_engine(engine_name)
        if not settings.cloud.api_key.strip():
            raise KeyError("CLOUD__API_KEY is not configured")
        return get_engine(engine_name)(
            api_key=settings.cloud.api_key, model=settings.cloud.model
        )
    raise KeyError(f"transcription engine {engine_name!r} is not registered")
