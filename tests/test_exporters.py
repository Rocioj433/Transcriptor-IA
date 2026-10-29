import io
import json
import zipfile

import pytest

import exporters
from exporters.base import fmt_timestamp, get_format
from exporters.srt import to_srt
from exporters.vtt import to_vtt
from engines.schema import Transcript
from tests.conftest import make_transcript


def test_eight_formats_are_registered():
    assert set(exporters.supported_formats()) == {
        "txt",
        "srt",
        "vtt",
        "docx",
        "pdf",
        "json",
        "csv",
        "md",
    }


def test_unknown_format_raises():
    with pytest.raises(KeyError):
        get_format("ass")


def test_timestamp_formats():
    assert fmt_timestamp(0.5, ",") == "00:00:00,500"
    assert fmt_timestamp(65.25, ",") == "00:01:05,250"
    assert fmt_timestamp(65.25, ".") == "00:01:05.250"
    assert fmt_timestamp(3661.999, ".") == "01:01:01.999"
    assert fmt_timestamp(-4, ".") == "00:00:00.000"


def test_srt_uses_comma_and_expected_cue():
    content = to_srt(make_transcript()).decode("utf-8")
    assert "1\n00:00:00,500 --> 00:00:05,000\nA: Hola, ¿cómo estás?" in content
    assert "3\n00:01:06,000 --> 00:01:10,000\nSin hablante asignado." in content


def test_vtt_uses_dot_and_speaker_tags():
    content = to_vtt(make_transcript()).decode("utf-8")
    assert content.startswith("WEBVTT\n")
    assert "00:00:00.500 --> 00:00:05.000" in content
    assert "<v A>Hola, ¿cómo estás?" in content


def test_golden_outputs_are_byte_stable(assert_golden):
    transcript = make_transcript()
    for fmt in ("txt", "srt", "vtt", "json", "csv", "md"):
        assert_golden(f"demo.{fmt}", exporters.render(fmt, transcript))


def test_json_roundtrip_and_metadata():
    payload = json.loads(exporters.render("json", make_transcript()))
    assert payload["file_name"] == "demo.mp3"
    assert payload["speakers"] == ["A", "B"]
    assert payload["segments"][0]["words"][0]["word"] == "Hola"


def test_csv_rows_and_quoting():
    content = exporters.render("csv", make_transcript()).decode("utf-8")
    lines = content.strip().splitlines()
    assert lines[0] == "id,start,end,speaker,text"
    assert lines[1] == '0,0.500,5.000,A,"Hola, ¿cómo estás?"'


def test_markdown_has_front_matter_and_segments():
    content = exporters.render("md", make_transcript()).decode("utf-8")
    assert content.startswith("# demo.mp3")
    assert "- **Language:** es" in content
    assert "**00:00:00.500** · **A** — Hola, ¿cómo estás?" in content


def test_docx_is_a_zip_package_and_deterministic():
    first = exporters.render("docx", make_transcript())
    second = exporters.render("docx", make_transcript())
    assert first.startswith(b"PK")
    assert first == second
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert "word/document.xml" in archive.namelist()


def test_pdf_is_deterministic():
    first = exporters.render("pdf", make_transcript())
    second = exporters.render("pdf", make_transcript())
    assert first.startswith(b"%PDF")
    assert first == second


def test_empty_transcript_is_valid_in_every_format():
    empty = Transcript(file_name="empty.mp3", duration=0.0, language="unknown", model_used="m")
    assert exporters.render("txt", empty) == b""
    assert exporters.render("srt", empty) == b""
    assert exporters.render("vtt", empty).startswith(b"WEBVTT")
    assert json.loads(exporters.render("json", empty))["segments"] == []
    assert exporters.render("docx", empty).startswith(b"PK")
    assert exporters.render("pdf", empty).startswith(b"%PDF")


def test_filename_for_uses_extension():
    assert exporters.filename_for("srt", "demo.mp3") == "demo.srt"
    assert exporters.filename_for("txt", "no-dots") == "no-dots.txt"
