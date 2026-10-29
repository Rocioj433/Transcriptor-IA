"""DOCX export (python-docx). Core properties are pinned for stable bytes."""

from __future__ import annotations

import io
from datetime import datetime

from docx import Document
from docx.shared import Pt

from exporters.base import clock_timestamp, register_format
from engines.schema import Transcript


@register_format(
    "docx",
    ".docx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)
def to_docx(transcript: Transcript) -> bytes:
    document = Document()
    properties = document.core_properties
    properties.title = transcript.file_name or "Transcription"
    properties.author = "Antigravity Studio"
    properties.last_modified_by = "Antigravity Studio"
    properties.created = datetime(2000, 1, 1, 0, 0, 0)
    properties.modified = datetime(2000, 1, 1, 0, 0, 0)
    properties.revision = 1

    heading = document.add_heading(transcript.file_name or "Transcription", level=1)
    heading.runs[0].font.size = Pt(20)

    meta = document.add_paragraph(
        f"Language: {transcript.language} | Model: {transcript.model_used} | "
        f"Duration: {clock_timestamp(transcript.duration)} | "
        f"Segments: {len(transcript.segments)}"
    )
    meta.runs[0].italic = True

    for segment in transcript.segments:
        paragraph = document.add_paragraph()
        stamp = paragraph.add_run(f"[{clock_timestamp(segment.start)}] ")
        stamp.bold = True
        if segment.speaker:
            speaker = paragraph.add_run(f"{segment.speaker}: ")
            speaker.bold = True
        paragraph.add_run(segment.text)

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
