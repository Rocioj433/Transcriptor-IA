"""Backup engine: openai-whisper (the reference PyTorch implementation)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from core.errors import CancelledError
from engines.base import register_engine
from engines.schema import Segment, Transcript, Word


class OpenAIWhisperEngine:
    name = "openai-whisper"

    def __init__(self, model_size: str = "large-v3-turbo", device: str = "cpu", model: Any | None = None) -> None:
        self.model_size = model_size
        self.device = device
        self._model = model

    def _load(self) -> Any:
        if self._model is None:
            try:
                import whisper
            except ImportError as exc:  # pragma: no cover - env dependent
                raise RuntimeError(
                    "openai-whisper is not installed; run: pip install openai-whisper"
                ) from exc
            self._model = whisper.load_model(self.model_size, device=self.device)
        return self._model

    def transcribe(
        self,
        path: Path,
        language: str | None = None,
        cancel: threading.Event | None = None,
    ) -> Transcript:
        model = self._load()
        options: dict[str, Any] = {"word_timestamps": True, "verbose": False}
        if language:
            options["language"] = language
        result = model.transcribe(str(path), **options)

        segments: list[Segment] = []
        for index, raw in enumerate(result.get("segments") or []):
            if cancel is not None and cancel.is_set():
                raise CancelledError("transcription cancelled")
            words = [
                Word(
                    index=word.get("id"),
                    word=str(word.get("word", "")).strip(),
                    start=float(word.get("start", 0.0)),
                    end=float(word.get("end", 0.0)),
                )
                for word in raw.get("words") or []
            ]
            segments.append(
                Segment(
                    id=index,
                    start=float(raw.get("start", 0.0)),
                    end=float(raw.get("end", 0.0)),
                    text=str(raw.get("text", "")).strip(),
                    confidence=round(max(0.0, 1.0 - float(raw.get("no_speech_prob", 0.0))), 4),
                    words=words,
                )
            )
        duration = float((result.get("segments") or [{}])[-1].get("end", 0.0)) if segments else 0.0
        return Transcript(
            file_name=Path(path).name,
            duration=duration,
            language=str(result.get("language") or language or "unknown"),
            model_used=f"openai-whisper:{self.model_size}",
            segments=segments,
        )


def register() -> None:
    register_engine(OpenAIWhisperEngine.name, OpenAIWhisperEngine)
