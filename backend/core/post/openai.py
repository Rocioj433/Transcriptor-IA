"""OpenAI post-processor (opt-in cloud LLM)."""

from __future__ import annotations

from typing import Any

from core.post.base import apply_cleanup, build_prompt
from engines.schema import Transcript


class OpenAIPostProcessor:
    name = "openai"

    def __init__(
        self,
        api_key: str = "",
        model: str = "gpt-4o-mini",
        client: Any | None = None,
    ) -> None:
        if client is None and not api_key.strip():
            raise ValueError("CLOUD__API_KEY is required for the openai post-processor")
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

    def cleanup(self, transcript: Transcript) -> Transcript:
        client = self._load_client()
        completion = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You edit transcripts and answer only with JSON."},
                {"role": "user", "content": build_prompt(transcript)},
            ],
            temperature=0,
        )
        response = completion.choices[0].message.content or ""
        return apply_cleanup(transcript, response)
