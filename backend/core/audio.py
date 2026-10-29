"""Audio helpers: ffmpeg discovery, duration probing and 16 kHz mono extraction."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import wave
from pathlib import Path

from core.errors import AudioError, CancelledError


def _winget_candidates(name: str) -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = [
        local / "Microsoft" / "WinGet" / "Links" / f"{name}.exe",
        Path(f"C:/Program Files/ffmpeg/bin/{name}.exe"),
        Path(f"C:/ffmpeg/bin/{name}.exe"),
    ]
    packages = local / "Microsoft" / "WinGet" / "Packages"
    if packages.is_dir():
        candidates.extend(sorted(packages.glob(f"Gyan.FFmpeg*/**/bin/{name}.exe")))
    return candidates


def find_binary(name: str) -> str | None:
    """Locate ``ffmpeg``/``ffprobe`` even when winget did not refresh PATH."""
    env_override = os.environ.get(f"{name.upper()}_BINARY")
    if env_override and Path(env_override).exists():
        return env_override
    found = shutil.which(name)
    if found:
        return found
    for candidate in _winget_candidates(name):
        if candidate.exists():
            return str(candidate)
    return None


def ffmpeg_available() -> bool:
    return find_binary("ffmpeg") is not None


def probe_duration(path: Path) -> float:
    """Return media duration in seconds, falling back to the WAV header."""
    path = Path(path)
    ffprobe = find_binary("ffprobe")
    if ffprobe:
        try:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "json",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if result.returncode == 0:
                return float(json.loads(result.stdout)["format"]["duration"])
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            pass
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as handle:
                return handle.getnframes() / float(handle.getframerate())
        except (OSError, wave.Error):
            return 0.0
    return 0.0


def _run_ffmpeg(command: list[str], cancel: threading.Event | None) -> None:
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        while True:
            if cancel is not None and cancel.is_set():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:  # pragma: no cover - defensive
                    process.kill()
                raise CancelledError("audio extraction cancelled")
            try:
                _, stderr = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode != 0:
            message = (stderr or b"").decode("utf-8", errors="replace").strip()
            raise AudioError(f"ffmpeg failed (exit {process.returncode}): {message[:400]}")
    finally:
        if process.poll() is None:  # pragma: no cover - defensive
            process.kill()


def ensure_wav(
    source: Path, workspace: Path, cancel: threading.Event | None = None
) -> Path:
    """Return a 16 kHz mono PCM WAV for ``source``.

    With ffmpeg installed the media is converted into ``workspace``. Without
    ffmpeg a ``.wav`` input is copied as-is (useful for tests / pre-converted
    files); any other format raises a clear ``AudioError``.
    """
    source = Path(source)
    if not source.exists():
        raise AudioError(f"media file not found: {source}")
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    destination = workspace / "audio.wav"
    ffmpeg = find_binary("ffmpeg")
    if ffmpeg:
        _run_ffmpeg(
            [
                ffmpeg,
                "-y",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(destination),
            ],
            cancel,
        )
        return destination
    if source.suffix.lower() == ".wav":
        shutil.copyfile(source, destination)
        return destination
    raise AudioError(
        "ffmpeg is required to process "
        f"{source.suffix or 'this file type'}; install ffmpeg and retry"
    )
