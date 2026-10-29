"""pyannote.audio diarizer implementation.

The pipeline is loaded lazily; a missing token, missing dependency or a
gated-model error is surfaced as ``DiarizationUnavailable`` so the job can
still finish with a raw transcript.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from core.diarizer.base import SpeakerSpan
from core.diarizer.lock import diarize_lock
from core.errors import CancelledError, DiarizationUnavailable


class PyannoteDiarizer:
    name = "pyannote"

    def __init__(
        self,
        token: str = "",
        model_name: str = "pyannote/speaker-diarization-3.1",
        pipeline: Any | None = None,
    ) -> None:
        self.token = token.strip()
        self.model_name = model_name
        self._pipeline = pipeline

    def _load(self) -> Any:
        if not self.token:
            raise DiarizationUnavailable("HUGGINGFACE_TOKEN is not configured")
        if self._pipeline is not None:
            return self._pipeline
        try:
            from pyannote.audio import Pipeline
        except ImportError as exc:
            raise DiarizationUnavailable(
                "pyannote.audio is not installed; run: pip install pyannote.audio"
            ) from exc
        try:
            try:
                self._pipeline = Pipeline.from_pretrained(self.model_name, token=self.token)
            except TypeError:  # pyannote < 3.1 uses another kwarg name
                self._pipeline = Pipeline.from_pretrained(
                    self.model_name, use_auth_token=self.token
                )
        except Exception as exc:  # network / gated repo / bad token
            raise DiarizationUnavailable(
                f"could not load pyannote model {self.model_name!r}: {exc}"
            ) from exc
        if self._pipeline is None:
            raise DiarizationUnavailable(
                f"pyannote returned no pipeline for {self.model_name!r}; "
                "accept the model terms on Hugging Face first"
            )
        return self._pipeline

    def diarize(
        self, path: Path, cancel: threading.Event | None = None
    ) -> list[SpeakerSpan]:
        pipeline = self._load()
        with diarize_lock(cancel):
            if cancel is not None and cancel.is_set():
                raise CancelledError("cancelled before diarization")
            try:
                annotation = pipeline(str(path))
            except Exception as exc:
                raise DiarizationUnavailable(f"diarization failed: {exc}") from exc

        entries: list[tuple[float, float, str]] = []
        for turn, _track, label in annotation.itertracks(yield_label=True):
            entries.append((float(turn.start), float(turn.end), str(label)))
        entries.sort(key=lambda item: (item[0], item[1]))

        labels: dict[str, str] = {}
        for _start, _end, label in entries:
            if label not in labels:
                labels[label] = _speaker_name(len(labels))
        return [
            SpeakerSpan(start=start, end=end, speaker=labels[label])
            for start, end, label in entries
        ]


def _speaker_name(index: int) -> str:
    """Map arbitrary pyannote labels to stable A, B, ... (then A1, B1, ...)."""
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    letter = letters[index % len(letters)]
    cycle = index // len(letters)
    return letter if cycle == 0 else f"{letter}{cycle}"
