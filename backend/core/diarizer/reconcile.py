"""Assign a speaker to each ASR segment by maximum temporal overlap."""

from __future__ import annotations

from core.diarizer.base import SpeakerSpan
from engines.schema import Segment


def overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))


def dominant_speaker(segment: Segment, spans: list[SpeakerSpan]) -> str | None:
    """Return the speaker with the largest overlap with ``segment``."""
    totals: dict[str, float] = {}
    first_seen: dict[str, float] = {}
    for span in spans:
        amount = overlap(segment.start, segment.end, span.start, span.end)
        if amount <= 0:
            continue
        totals[span.speaker] = totals.get(span.speaker, 0.0) + amount
        first_seen.setdefault(span.speaker, span.start)
    if not totals:
        return None
    best = max(totals, key=lambda speaker: (totals[speaker], -first_seen[speaker]))
    return best


def reconcile_speakers(
    segments: list[Segment], spans: list[SpeakerSpan]
) -> list[Segment]:
    """Return copies of ``segments`` with ``speaker`` resolved from ``spans``.

    Segments with no overlapping diarization span keep ``speaker=None`` so the
    raw transcript remains valid.
    """
    reconciled: list[Segment] = []
    for segment in segments:
        reconciled.append(
            Segment(
                id=segment.id,
                start=segment.start,
                end=segment.end,
                text=segment.text,
                speaker=dominant_speaker(segment, spans),
                confidence=segment.confidence,
                words=list(segment.words),
            )
        )
    return reconciled
