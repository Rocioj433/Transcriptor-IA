import pytest

from core.errors import IllegalTransition
from core.job import (
    ALLOWED_TRANSITIONS,
    PROGRESS,
    JobState,
    can_transition,
    coerce_state,
    transition,
)
from core.queue import Job


def make_job() -> Job:
    return Job(id="j1", file_name="a.mp3")


def test_progress_mapping_is_exact():
    assert PROGRESS[JobState.QUEUED] == 0
    assert PROGRESS[JobState.TRANSCRIBING] == 20
    assert PROGRESS[JobState.DIARIZING] == 50
    assert PROGRESS[JobState.POST] == 80
    assert PROGRESS[JobState.READY] == 100
    assert PROGRESS[JobState.ERROR] == -1
    assert PROGRESS[JobState.CANCELLED] == -1


def test_happy_path_transitions():
    job = make_job()
    for state in (
        JobState.TRANSCRIBING,
        JobState.DIARIZING,
        JobState.POST,
        JobState.READY,
    ):
        transition(job, state)
        assert job.status is state
        assert job.progress == PROGRESS[state]
    assert job.progress == 100


def test_illegal_transition_is_rejected():
    job = make_job()
    transition(job, JobState.READY)
    with pytest.raises(IllegalTransition):
        transition(job, JobState.TRANSCRIBING)


def test_same_state_is_noop():
    job = make_job()
    assert transition(job, JobState.QUEUED) is job
    assert job.progress == 0


def test_cancel_is_allowed_from_every_active_state():
    for state in (
        JobState.QUEUED,
        JobState.TRANSCRIBING,
        JobState.DIARIZING,
        JobState.POST,
    ):
        assert JobState.CANCELLED in ALLOWED_TRANSITIONS[state]
        job = make_job()
        job.status = state
        job.progress = PROGRESS[state]
        transition(job, JobState.CANCELLED, "cancelled")
        assert job.status is JobState.CANCELLED
        assert job.progress == -1
        assert job.message == "cancelled"


def test_terminal_states_have_no_exits():
    for state in (JobState.READY, JobState.ERROR, JobState.CANCELLED):
        assert ALLOWED_TRANSITIONS[state] == frozenset()


def test_coerce_and_can_transition():
    assert coerce_state("ready") is JobState.READY
    assert can_transition("queued", "transcribing")
    assert not can_transition("ready", "error")
