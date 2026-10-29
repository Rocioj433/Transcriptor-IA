import pytest

from core.job import JobState
from core.queue import JobRepository


def test_create_get_and_list(tmp_path):
    repo = JobRepository()
    first = repo.create("a.mp3", tmp_path / "a.mp3", uploaded=True, language="es")
    second = repo.create("b.mp3", tmp_path / "b.mp3")
    assert repo.get(first.id) is first
    assert repo.get("missing") is None
    assert repo.require(second.id) is second
    assert {job.id for job in repo.list()} == {first.id, second.id}
    assert repo.list()[0].created_at >= repo.list()[1].created_at


def test_require_missing_raises_keyerror():
    with pytest.raises(KeyError):
        JobRepository().require("nope")


def test_delete():
    repo = JobRepository()
    job = repo.create("a.mp3")
    assert repo.delete(job.id) is True
    assert repo.delete(job.id) is False
    assert repo.get(job.id) is None


def test_cancel_semantics():
    repo = JobRepository()
    job = repo.create("a.mp3")
    assert job.cancel() is True
    assert job.cancel_event.is_set()
    job.status = JobState.READY
    assert job.cancel() is False


def test_to_dict_shape():
    repo = JobRepository()
    job = repo.create("a.mp3", language="es")
    payload = job.to_dict()
    assert payload["id"] == job.id
    assert payload["status"] == "queued"
    assert payload["progress"] == 0
    assert payload["transcript"] is None
    assert payload["file_name"] == "a.mp3"
    assert payload["language"] == "es"


def test_is_terminal():
    repo = JobRepository()
    job = repo.create("a.mp3")
    assert not job.is_terminal
    job.status = JobState.CANCELLED
    assert job.is_terminal
