"""CSV export — one row per segment."""

from __future__ import annotations

import csv
import io

from exporters.base import register_format
from engines.schema import Transcript


@register_format("csv", ".csv", "text/csv; charset=utf-8")
def to_csv(transcript: Transcript) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["id", "start", "end", "speaker", "text"])
    for segment in transcript.segments:
        writer.writerow(
            [
                segment.id,
                f"{segment.start:.3f}",
                f"{segment.end:.3f}",
                segment.speaker or "",
                segment.text,
            ]
        )
    return buffer.getvalue().encode("utf-8")
