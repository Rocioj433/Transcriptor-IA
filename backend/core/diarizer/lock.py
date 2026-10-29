"""Global diarization lock.

pyannote/torch pipelines are not safe to run concurrently (especially on CUDA),
so every diarization call is serialized through a single process-wide lock.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from core.errors import CancelledError

DIARIZE_LOCK = threading.Lock()


@contextmanager
def diarize_lock(
    cancel: threading.Event | None = None, poll_interval: float = 0.1
) -> Iterator[None]:
    """Acquire ``DIARIZE_LOCK`` while honouring cancellation."""
    while not DIARIZE_LOCK.acquire(timeout=poll_interval):
        if cancel is not None and cancel.is_set():
            raise CancelledError("cancelled while waiting for the diarization lock")
    try:
        if cancel is not None and cancel.is_set():
            raise CancelledError("cancelled before diarization")
        yield
    finally:
        DIARIZE_LOCK.release()
