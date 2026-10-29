"""SubRip (.srt) export — timestamps use ``HH:MM:SS,mmm``."""

from __future__ import annotations

from exporters.base import fmt_timestamp, register_format
from engines.schema import Transcript


def _cue_text(segment) -> str:
    if segment.speaker:
        return f"{segment.speaker}: {segment.text}".strip()
    return segment.text.strip()


@register_format("srt", ".srt", "application/x-subrip; charset=utf-8")
def to_srt(transcript: Transcript) -> bytes:
    blocks: list[str] = []
    for index, segment in enumerate(transcript.segments, start=1):
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{fmt_timestamp(segment.start, ',')} --> {fmt_timestamp(segment.end, ',')}",
                    _cue_text(segment),
                ]
            )
        )
    if not blocks:
        return b""
    return ("\n\n".join(blocks) + "\n").encode("utf-8")
