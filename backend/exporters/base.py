"""Export format registry.

Every renderer is a pure function ``Transcript -> bytes`` so outputs are
deterministic and golden-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from engines.schema import Transcript

Renderer = Callable[[Transcript], bytes]


@dataclass(frozen=True)
class FormatSpec:
    key: str
    extension: str
    mime: str
    render: Renderer


FORMATS: dict[str, FormatSpec] = {}


def register_format(key: str, extension: str, mime: str) -> Callable[[Renderer], Renderer]:
    def decorator(func: Renderer) -> Renderer:
        FORMATS[key] = FormatSpec(key=key, extension=extension, mime=mime, render=func)
        return func

    return decorator


def supported_formats() -> list[str]:
    return list(FORMATS)


def get_format(key: str) -> FormatSpec:
    try:
        return FORMATS[key]
    except KeyError as exc:
        raise KeyError(f"unsupported export format {key!r}") from exc


def render(key: str, transcript: Transcript) -> bytes:
    return get_format(key).render(transcript)


def filename_for(key: str, base_name: str) -> str:
    stem = base_name.rsplit(".", 1)[0] if "." in base_name else base_name
    return f"{stem}{get_format(key).extension}"


def fmt_timestamp(seconds: float, separator: str = ".") -> str:
    """Format ``HH:MM:SS<sep>mmm`` (SRT uses a comma, VTT a dot)."""
    total_ms = int(round(max(0.0, seconds) * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def clock_timestamp(seconds: float) -> str:
    return fmt_timestamp(seconds, ".")
