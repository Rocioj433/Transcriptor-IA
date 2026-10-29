"""Domain errors shared by the pipeline, API and workers."""

from __future__ import annotations


class TranscriptorError(Exception):
    """Base class for expected application errors."""


class CancelledError(TranscriptorError):
    """Raised when a job is cancelled cooperatively."""


class AudioError(TranscriptorError):
    """Raised when ffmpeg is missing or audio extraction fails."""


class DiarizationUnavailable(TranscriptorError):
    """Raised when speaker diarization cannot run (token/model/deps).

    The pipeline treats this as a soft failure: the job still finishes as
    ``ready`` with unassigned speakers and a warning.
    """


class IllegalTransition(TranscriptorError):
    """Raised when an invalid job state transition is attempted."""
