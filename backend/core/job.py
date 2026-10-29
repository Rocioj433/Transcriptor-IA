"""Job lifecycle: states, progress mapping and guarded transitions."""

from __future__ import annotations

from enum import Enum
from typing import Any

from core.errors import IllegalTransition


class JobState(str, Enum):
    QUEUED = "queued"
    TRANSCRIBING = "transcribing"
    DIARIZING = "diarizing"
    POST = "post"
    READY = "ready"
    ERROR = "error"
    CANCELLED = "cancelled"


PROGRESS: dict[JobState, int] = {
    JobState.QUEUED: 0,
    JobState.TRANSCRIBING: 20,
    JobState.DIARIZING: 50,
    JobState.POST: 80,
    JobState.READY: 100,
    JobState.ERROR: -1,
    JobState.CANCELLED: -1,
}

TERMINAL_STATES = frozenset({JobState.READY, JobState.ERROR, JobState.CANCELLED})

ALLOWED_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.QUEUED: frozenset(
        {JobState.TRANSCRIBING, JobState.DIARIZING, JobState.POST, JobState.READY, JobState.ERROR, JobState.CANCELLED}
    ),
    JobState.TRANSCRIBING: frozenset(
        {JobState.DIARIZING, JobState.POST, JobState.READY, JobState.ERROR, JobState.CANCELLED}
    ),
    JobState.DIARIZING: frozenset(
        {JobState.POST, JobState.READY, JobState.ERROR, JobState.CANCELLED}
    ),
    JobState.POST: frozenset({JobState.READY, JobState.ERROR, JobState.CANCELLED}),
    JobState.READY: frozenset(),
    JobState.ERROR: frozenset(),
    JobState.CANCELLED: frozenset(),
}


def coerce_state(value: JobState | str) -> JobState:
    return value if isinstance(value, JobState) else JobState(value)


def can_transition(current: JobState | str, target: JobState | str) -> bool:
    return coerce_state(target) in ALLOWED_TRANSITIONS[coerce_state(current)]


def transition(job: Any, target: JobState | str, message: str | None = None) -> Any:
    """Mutate ``job`` to ``target`` if the transition is legal.

    Raises ``IllegalTransition`` for unknown/illegal moves. Re-applying the
    current state is a no-op.
    """
    current = coerce_state(job.status)
    new_state = coerce_state(target)
    if new_state == current:
        return job
    if new_state not in ALLOWED_TRANSITIONS[current]:
        raise IllegalTransition(f"cannot transition {current.value} -> {new_state.value}")
    job.status = new_state
    job.progress = PROGRESS[new_state]
    if message is not None:
        job.message = message
    return job
