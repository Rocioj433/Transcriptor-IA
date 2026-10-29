import wave

import pytest

from core import audio
from core.audio import ensure_wav, find_binary, probe_duration
from core.errors import AudioError


def test_probe_duration_reads_wav_header(wav_file):
    assert probe_duration(wav_file) == pytest.approx(1.0, abs=0.01)


def test_probe_duration_missing_file_returns_zero(tmp_path):
    assert probe_duration(tmp_path / "nope.wav") == 0.0


def test_ensure_wav_missing_source_raises(tmp_path):
    with pytest.raises(AudioError, match="not found"):
        ensure_wav(tmp_path / "nope.wav", tmp_path / "work")


def test_ensure_wav_copies_wav_without_ffmpeg(monkeypatch, wav_file, tmp_path):
    monkeypatch.setattr(audio, "find_binary", lambda name: None)
    destination = ensure_wav(wav_file, tmp_path / "work")
    assert destination.exists()
    assert destination.name == "audio.wav"
    with wave.open(str(destination), "rb") as handle:
        assert handle.getframerate() == 16000


def test_ensure_wav_requires_ffmpeg_for_other_formats(monkeypatch, tmp_path):
    source = tmp_path / "clip.mp3"
    source.write_bytes(b"fake")
    monkeypatch.setattr(audio, "find_binary", lambda name: None)
    with pytest.raises(AudioError, match="ffmpeg is required"):
        ensure_wav(source, tmp_path / "work")


def test_find_binary_env_override(monkeypatch, tmp_path):
    fake = tmp_path / "ffmpeg.exe"
    fake.write_bytes(b"binary")
    monkeypatch.setenv("FFMPEG_BINARY", str(fake))
    assert find_binary("ffmpeg") == str(fake)


def test_real_ffmpeg_extracts_16k_mono_wav(wav_file, tmp_path):
    if not audio.ffmpeg_available():
        pytest.skip("ffmpeg is not installed")
    destination = ensure_wav(wav_file, tmp_path / "work")
    with wave.open(str(destination), "rb") as handle:
        assert handle.getframerate() == 16000
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2

