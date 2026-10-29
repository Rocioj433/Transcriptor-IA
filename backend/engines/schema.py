"""Common transcript schema shared by every transcription engine.

All engines MUST return these dataclasses so exporters, the API and the
frontend never depend on a specific provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Word:
    """A single word with its time span (seconds)."""

    index: int | None
    word: str
    start: float
    end: float

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "word": self.word, "start": self.start, "end": self.end}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Word":
        return cls(
            index=data.get("index"),
            word=data["word"],
            start=float(data["start"]),
            end=float(data["end"]),
        )


@dataclass
class Segment:
    """A transcript segment, optionally attributed to a speaker."""

    id: int
    start: float
    end: float
    text: str
    speaker: str | None = None
    confidence: float = 0.0
    words: list[Word] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "speaker": self.speaker,
            "confidence": self.confidence,
            "words": [w.to_dict() for w in self.words],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Segment":
        return cls(
            id=int(data["id"]),
            start=float(data["start"]),
            end=float(data["end"]),
            text=data.get("text", ""),
            speaker=data.get("speaker"),
            confidence=float(data.get("confidence") or 0.0),
            words=[Word.from_dict(w) for w in data.get("words") or []],
        )


@dataclass
class Transcript:
    """Full transcription result for one media file."""

    file_name: str
    duration: float
    language: str
    model_used: str
    segments: list[Segment] = field(default_factory=list)
    raw_segments: list[Segment] | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(segment.text.strip() for segment in self.segments if segment.text.strip())

    @property
    def speakers(self) -> list[str]:
        seen: list[str] = []
        for segment in self.segments:
            if segment.speaker and segment.speaker not in seen:
                seen.append(segment.speaker)
        return seen

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "file_name": self.file_name,
            "duration": self.duration,
            "language": self.language,
            "model_used": self.model_used,
            "text": self.text,
            "speakers": self.speakers,
            "segments": [s.to_dict() for s in self.segments],
            "warnings": list(self.warnings),
        }
        if self.raw_segments is not None:
            data["raw_segments"] = [s.to_dict() for s in self.raw_segments]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Transcript":
        raw = data.get("raw_segments")
        return cls(
            file_name=data.get("file_name", ""),
            duration=float(data.get("duration") or 0.0),
            language=data.get("language", "unknown"),
            model_used=data.get("model_used", "unknown"),
            segments=[Segment.from_dict(s) for s in data.get("segments") or []],
            raw_segments=[Segment.from_dict(s) for s in raw] if raw is not None else None,
            warnings=list(data.get("warnings") or []),
        )
