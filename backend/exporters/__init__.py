"""Exporter package: importing it registers every supported format."""

from exporters.base import FORMATS, FormatSpec, filename_for, get_format, render, supported_formats

# Importing the modules below executes their ``@register_format`` decorators.
from exporters import csv_exporter, docx, json_exporter, md, pdf, srt, txt, vtt  # noqa: E402,F401

__all__ = [
    "FORMATS",
    "FormatSpec",
    "filename_for",
    "get_format",
    "render",
    "supported_formats",
]
