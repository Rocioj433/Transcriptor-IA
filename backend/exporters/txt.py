"""Plain text export."""

from __future__ import annotations

from exporters.base import clock_timestamp, register_format
from engines.schema import Transcript


@register_format("txt", ".txt", "text/plain; charset=utf-8")
def to_txt(transcript: Transcript) -> bytes:
    lines: list[str] = []
    for segment in transcript.segments:
        prefix = f"[{clock_timestamp(segment.start)}] "
        if segment.speaker:
            prefix += f"{segment.speaker}: "
        lines.append(f"{prefix}{segment.text}".rstrip())
    if not lines:
        return b""
    return ("\n".join(lines) + "\n").encode("utf-8")
