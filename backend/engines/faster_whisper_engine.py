"""Default engine: faster-whisper (CTranslate2).

The model is loaded lazily and cached per instance so importing this module
never requires the ML wheels (tests inject a fake model instead).
"""

from __future__ import annotations

import math
import threading
from pathlib import Path
from typing import Any

from core.errors import CancelledError
from engines.base import register_engine
from engines.schema import Segment, Transcript, Word


class FasterWhisperEngine:
    name = "faster-whisper"

    def __init__(
        self,
        model_size: str = "large-v3-turbo",
        device: str = "cpu",
        compute_type: str = "int8",
        model: Any | None = None,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = model

    def _load(self) -> Any:
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # pragma: no cover - env dependent
                raise RuntimeError(
                    "faster-whisper is not installed; run: pip install faster-whisper"
                ) from exc
            self._model = WhisperModel(
                self.model_size, device=self.device, compute_type=self.compute_type
            )
        return self._model

    def transcribe(
        self,
        path: Path,
        language: str | None = None,
        cancel: threading.Event | None = None,
    ) -> Transcript:
        model = self._load()
        raw_segments, info = model.transcribe(
            str(path),
            language=language,
            vad_filter=True,
            word_timestamps=True,
            beam_size=5,
        )

        segments: list[Segment] = []
        last_end = 0.0
        for index, raw in enumerate(raw_segments):
            if cancel is not None and cancel.is_set():
                raise CancelledError("transcription cancelled")
            words = [
                Word(
                    index=getattr(word, "index", None),
                    word=word.word,
                    start=float(word.start),
                    end=float(word.end),
                )
                for word in (getattr(raw, "words", None) or [])
            ]
            confidence = 0.0
            avg_logprob = getattr(raw, "avg_logprob", None)
            if avg_logprob is not None:
                confidence = round(min(1.0, max(0.0, math.exp(float(avg_logprob)))), 4)
            segment = Segment(
                id=index,
                start=float(raw.start),
                end=float(raw.end),
                text=str(raw.text).strip(),
                confidence=confidence,
                words=words,
            )
            segments.append(segment)
            last_end = max(last_end, segment.end)

        duration = float(getattr(info, "duration", 0.0) or last_end)
        detected = getattr(info, "language", None) or language or "unknown"
        return Transcript(
            file_name=Path(path).name,
            duration=duration,
            language=str(detected),
            model_used=self.model_size,
            segments=segments,
        )


def register() -> None:
    register_engine(FasterWhisperEngine.name, FasterWhisperEngine)
