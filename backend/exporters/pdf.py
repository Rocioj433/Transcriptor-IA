"""PDF export (reportlab).

``invariant=1`` removes timestamps and random document ids so repeated runs
produce byte-identical files.
"""

from __future__ import annotations

import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from exporters.base import clock_timestamp, register_format
from engines.schema import Transcript

MARGIN = 48
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
SIZE = 10
LEADING = 14


def _safe(text: str) -> str:
    """Keep only characters representable by the built-in WinAnsi font."""
    return text.encode("cp1252", errors="replace").decode("cp1252")


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if stringWidth(candidate, font, size) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


@register_format("pdf", ".pdf", "application/pdf")
def to_pdf(transcript: Transcript) -> bytes:
    buffer = io.BytesIO()
    page_width, page_height = A4
    pdf = canvas.Canvas(buffer, pagesize=A4, invariant=1)
    pdf.setTitle(_safe(transcript.file_name or "Transcription"))
    pdf.setAuthor("Antigravity Studio")
    pdf.setSubject("Transcription")
    pdf.setCreator("Antigravity Studio")

    width = page_width - 2 * MARGIN
    y = page_height - MARGIN

    def new_page_if_needed(needed: float = LEADING) -> None:
        nonlocal y
        if y - needed < MARGIN:
            pdf.showPage()
            y = page_height - MARGIN

    pdf.setFont(FONT_BOLD, 16)
    pdf.drawString(MARGIN, y, _safe(transcript.file_name or "Transcription"))
    y -= 24

    pdf.setFont(FONT, 9)
    meta = (
        f"Language: {transcript.language} | Model: {transcript.model_used} | "
        f"Duration: {clock_timestamp(transcript.duration)} | "
        f"Segments: {len(transcript.segments)}"
    )
    for line in _wrap(_safe(meta), FONT, 9, width):
        pdf.drawString(MARGIN, y, line)
        y -= 12
    y -= 6

    for segment in transcript.segments:
        prefix = f"[{clock_timestamp(segment.start)}] "
        if segment.speaker:
            prefix += f"{segment.speaker}: "
        for index, line in enumerate(_wrap(_safe(prefix + segment.text), FONT, SIZE, width)):
            new_page_if_needed()
            pdf.setFont(FONT_BOLD if index == 0 else FONT, SIZE)
            pdf.drawString(MARGIN, y, line)
            y -= LEADING

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
