"""Ollama post-processor (local LLM, default provider)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable

from core.post.base import build_prompt, apply_cleanup
from engines.schema import Transcript


class OllamaPostProcessor:
    name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1",
        timeout_s: float = 60.0,
        client: Callable[[str], str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self._client = client

    def _request(self, prompt: str) -> str:
        if self._client is not None:
            return self._client(prompt)
        payload = json.dumps(
            {"model": self.model, "prompt": prompt, "stream": False, "format": "json"}
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"ollama request failed: {exc}") from exc
        return str(body.get("response", ""))

    def cleanup(self, transcript: Transcript) -> Transcript:
        return apply_cleanup(transcript, self._request(build_prompt(transcript)))
