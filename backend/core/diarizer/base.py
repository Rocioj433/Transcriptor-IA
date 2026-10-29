"""Diarizer SPI: return who spoke when, independently of the ASR engine."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SpeakerSpan:
    start: float
    end: float
    speaker: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@runtime_checkable
class Diarizer(Protocol):
    name: str

    def diarize(
        self, path: Path, cancel: threading.Event | None = None
    ) -> list[SpeakerSpan]:  # pragma: no cover - protocol definition
        ...
