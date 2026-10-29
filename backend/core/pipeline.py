"""Synchronous pipeline: extract -> transcribe -> diarize -> reconcile -> post."""

from __future__ import annotations

import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.audio import ensure_wav, probe_duration
from core.diarizer.base import SpeakerSpan
from core.diarizer.reconcile import reconcile_speakers
from core.errors import CancelledError, DiarizationUnavailable
from core.job import JobState, transition
from engines.base import TranscriptionEngine
from engines.schema import Transcript


class Pipeline:
    def __init__(
        self,
        engine: TranscriptionEngine,
        diarizer: Any | None = None,
        post_processor: Any | None = None,
        settings: Any | None = None,
        audio_extractor: Callable[..., Path] = ensure_wav,
        duration_probe: Callable[[Path], float] = probe_duration,
    ) -> None:
        self.engine = engine
        self.diarizer = diarizer
        self.post_processor = post_processor
        self.settings = settings
        self._extract = audio_extractor
        self._probe = duration_probe

    @staticmethod
    def _check(job: Any) -> None:
        if job.cancel_event.is_set():
            raise CancelledError("job cancelled")

    def run(self, job: Any) -> Transcript:
        self._check(job)
        transition(job, JobState.TRANSCRIBING)
        job.touch()

        with tempfile.TemporaryDirectory(prefix="antigravity-") as workspace:
            wav_path = self._extract(job.media_path, Path(workspace), job.cancel_event)
            self._check(job)

            transcript = self.engine.transcribe(
                wav_path, language=job.language, cancel=job.cancel_event
            )
            transcript.file_name = job.file_name or transcript.file_name
            if transcript.duration <= 0:
                transcript.duration = float(self._probe(job.media_path) or 0.0)
            self._check(job)

            transition(job, JobState.DIARIZING)
            job.touch()
            spans = self._diarize(wav_path, job, transcript)
            if spans:
                transcript.segments = reconcile_speakers(transcript.segments, spans)
            self._check(job)

            if self.post_processor is not None:
                transition(job, JobState.POST)
                job.touch()
                transcript = self._post_process(transcript)

            self._check(job)
            transition(job, JobState.READY)
            if not transcript.warnings:
                job.message = None
            else:
                job.message = "; ".join(transcript.warnings)
            job.transcript = transcript
            job.touch()
            return transcript

    def _diarize(
        self, wav_path: Path, job: Any, transcript: Transcript
    ) -> list[SpeakerSpan]:
        if self.diarizer is None:
            transcript.warnings.append(
                "diarization-unavailable: no diarizer configured"
            )
            return []
        try:
            return self.diarizer.diarize(wav_path, job.cancel_event)
        except CancelledError:
            raise
        except DiarizationUnavailable as exc:
            transcript.warnings.append(f"diarization-unavailable: {exc}")
            return []
        except Exception as exc:  # never fail the job for optional diarization
            transcript.warnings.append(f"diarization-unavailable: {exc}")
            return []

    def _post_process(self, transcript: Transcript) -> Transcript:
        try:
            return self.post_processor.cleanup(transcript)
        except Exception as exc:  # never block the result on the optional LLM
            transcript.warnings.append(f"post-process-unavailable: {exc}")
            return transcript
