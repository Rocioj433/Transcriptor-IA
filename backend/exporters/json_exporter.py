"""Structured JSON export (full transcript, word timestamps included)."""

from __future__ import annotations

import json

from exporters.base import register_format
from engines.schema import Transcript


@register_format("json", ".json", "application/json; charset=utf-8")
def to_json(transcript: Transcript) -> bytes:
    payload = transcript.to_dict()
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
