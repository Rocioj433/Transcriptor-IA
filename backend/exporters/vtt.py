"""WebVTT (.vtt) export — timestamps use ``HH:MM:SS.mmm``."""

from __future__ import annotations

from exporters.base import fmt_timestamp, register_format
from engines.schema import Transcript


@register_format("vtt", ".vtt", "text/vtt; charset=utf-8")
def to_vtt(transcript: Transcript) -> bytes:
    lines: list[str] = ["WEBVTT", ""]
    for segment in transcript.segments:
        lines.append(
            f"{fmt_timestamp(segment.start, '.')} --> {fmt_timestamp(segment.end, '.')}"
        )
        if segment.speaker:
            lines.append(f"<v {segment.speaker}>{segment.text}")
        else:
            lines.append(segment.text)
        lines.append("")
    return ("\n".join(lines) + "\n").encode("utf-8")
