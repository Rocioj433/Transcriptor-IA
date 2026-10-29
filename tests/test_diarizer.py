import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from core.diarizer.lock import DIARIZE_LOCK, diarize_lock
from core.diarizer.pyannote import PyannoteDiarizer, _speaker_name
from core.errors import CancelledError, DiarizationUnavailable


class FakeAnnotation:
    def __init__(self, entries):
        self.entries = entries

    def itertracks(self, yield_label=False):
        for start, end, label in self.entries:
            yield SimpleNamespace(start=start, end=end), None, label


class FakePipeline:
    def __init__(self, entries, delay: float = 0.0):
        self.entries = entries
        self.delay = delay
        self.calls = 0
        self.active = 0
        self.max_active = 0
        self._guard = threading.Lock()

    def __call__(self, path):
        with self._guard:
            self.calls += 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            return FakeAnnotation(self.entries)
        finally:
            with self._guard:
                self.active -= 1


def test_missing_token_is_unavailable():
    with pytest.raises(DiarizationUnavailable, match="HUGGINGFACE_TOKEN"):
        PyannoteDiarizer(token="").diarize("audio.wav")


def test_fake_pipeline_labels_are_normalized_and_sorted():
    pipeline = FakePipeline([(5.0, 8.0, "SPEAKER_07"), (0.0, 4.0, "SPEAKER_02")])
    diarizer = PyannoteDiarizer(token="hf_x", pipeline=pipeline)
    spans = diarizer.diarize("audio.wav")
    assert [(span.start, span.end, span.speaker) for span in spans] == [
        (0.0, 4.0, "A"),
        (5.0, 8.0, "B"),
    ]


def test_global_lock_serializes_pipeline_calls():
    entries = [(0.0, 1.0, "SPEAKER_00")]
    pipeline = FakePipeline(entries, delay=0.1)
    diarizer = PyannoteDiarizer(token="hf_x", pipeline=pipeline)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: diarizer.diarize("audio.wav"), range(2)))
    assert pipeline.calls == 2
    assert pipeline.max_active == 1


def test_waiting_for_lock_honours_cancel():
    assert DIARIZE_LOCK.acquire(timeout=1)
    try:
        cancel = threading.Event()
        cancel.set()
        with pytest.raises(CancelledError):
            with diarize_lock(cancel, poll_interval=0.01):
                pass
    finally:
        DIARIZE_LOCK.release()


def test_speaker_name_cycles_after_z():
    assert _speaker_name(0) == "A"
    assert _speaker_name(25) == "Z"
    assert _speaker_name(26) == "A1"


def test_pipeline_failure_becomes_unavailable():
    class Boom:
        def __call__(self, path):
            raise RuntimeError("cuda exploded")

    with pytest.raises(DiarizationUnavailable, match="cuda exploded"):
        PyannoteDiarizer(token="hf_x", pipeline=Boom()).diarize("audio.wav")
