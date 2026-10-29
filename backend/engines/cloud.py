"""Cloud fallback engine: OpenAI gpt-4o-transcribe (opt-in, needs an API key)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from core.errors import CancelledError
from engines.base import register_engine
from engines.schema import Segment, Transcript, Word


class CloudTranscribeEngine:
    name = "cloud-transcribe"

    def __init__(
        self,
        api_key: str = "",
        model: str = "gpt-4o-transcribe",
        client: Any | None = None,
    ) -> None:
        if client is None and not api_key.strip():
            raise ValueError("CLOUD__API_KEY is required for the cloud-transcribe engine")
        self.api_key = api_key
        self.model = model
        self._client = client

    def _load_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover - env dependent
                raise RuntimeError("openai is not installed; run: pip install openai") from exc
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def transcribe(
        self,
        path: Path,
        language: str | None = None,
        cancel: threading.Event | None = None,
    ) -> Transcript:
        if cancel is not None and cancel.is_set():
            raise CancelledError("transcription cancelled")
        client = self._load_client()
        options: dict[str, Any] = {
            "model": self.model,
            "response_format": "verbose_json",
            "timestamp_granularities": ["segment", "word"],
        }
        if language:
            options["language"] = language
        with open(path, "rb") as handle:
            response = client.audio.transcriptions.create(file=handle, **options)

        data = response if isinstance(response, dict) else response.model_dump()
        raw_segments = data.get("segments") or []
        raw_words = data.get("words") or []
        segments: list[Segment] = []
        if raw_segments:
            for index, raw in enumerate(raw_segments):
                if cancel is not None and cancel.is_set():
                    raise CancelledError("transcription cancelled")
                start = float(raw.get("start", 0.0))
                end = float(raw.get("end", 0.0))
                words = [
                    Word(
                        index=word.get("id"),
                        word=str(word.get("word", "")).strip(),
                        start=float(word.get("start", 0.0)),
                        end=float(word.get("end", 0.0)),
                    )
                    for word in raw_words
                    if start <= float(word.get("start", 0.0)) <= end
                ]
                segments.append(
                    Segment(
                        id=index,
                        start=start,
                        end=end,
                        text=str(raw.get("text", "")).strip(),
                        words=words,
                    )
                )
        else:
            text = str(data.get("text", "")).strip()
            duration = float(data.get("duration") or 0.0)
            if text:
                segments.append(
                    Segment(id=0, start=0.0, end=duration, text=text, words=[])
                )
        duration = float(data.get("duration") or (segments[-1].end if segments else 0.0))
        return Transcript(
            file_name=Path(path).name,
            duration=duration,
            language=str(data.get("language") or language or "unknown"),
            model_used=self.model,
            segments=segments,
        )


def register() -> None:
    register_engine(CloudTranscribeEngine.name, CloudTranscribeEngine)
