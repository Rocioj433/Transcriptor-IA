"""Markdown export."""

from __future__ import annotations

from exporters.base import clock_timestamp, register_format
from engines.schema import Transcript


@register_format("md", ".md", "text/markdown; charset=utf-8")
def to_markdown(transcript: Transcript) -> bytes:
    lines: list[str] = [
        f"# {transcript.file_name or 'Transcription'}",
        "",
        f"- **Language:** {transcript.language}",
        f"- **Model:** {transcript.model_used}",
        f"- **Duration:** {clock_timestamp(transcript.duration)}",
        f"- **Segments:** {len(transcript.segments)}",
        "",
    ]
    for segment in transcript.segments:
        speaker = f" · **{segment.speaker}**" if segment.speaker else ""
        lines.append(f"**{clock_timestamp(segment.start)}**{speaker} — {segment.text}")
        lines.append("")
    return ("\n".join(lines).rstrip() + "\n").encode("utf-8")
