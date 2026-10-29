"""Background worker pool consuming the in-process job queue."""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any

from core.errors import CancelledError
from core.job import JobState, transition
from core.queue import Job, JobRepository


class Worker:
    def __init__(self, repository: JobRepository, pipeline: Any, workers: int = 2) -> None:
        self.repository = repository
        self.pipeline = pipeline
        self.workers = max(1, int(workers))
        self._queue: queue.Queue[Job] = queue.Queue()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> "Worker":
        if self._threads:
            return self
        self._stop.clear()
        for index in range(self.workers):
            thread = threading.Thread(
                target=self._loop, name=f"antigravity-worker-{index}", daemon=True
            )
            thread.start()
            self._threads.append(thread)
        return self

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=timeout)
        self._threads.clear()

    @property
    def running(self) -> bool:
        return any(thread.is_alive() for thread in self._threads)

    def submit(self, job: Job) -> Job:
        self._queue.put(job)
        return job

    def pending(self) -> int:
        return self._queue.qsize()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._process(job)
            finally:
                self._queue.task_done()

    def _process(self, job: Job) -> None:
        if job.cancel_event.is_set():
            self._cancel(job)
            return
        try:
            self.pipeline.run(job)
            if job.cancel_event.is_set() and not job.is_terminal:
                self._cancel(job)
        except CancelledError:
            self._cancel(job)
        except Exception as exc:  # noqa: BLE001 - boundary: any failure ends the job
            self._fail(job, exc)
        finally:
            self.repository.update(job)

    def _cancel(self, job: Job) -> None:
        if job.is_terminal:
            return
        transition(job, JobState.CANCELLED, "cancelled")
        self._cleanup(job)

    def _fail(self, job: Job, exc: Exception) -> None:
        job.error = f"{type(exc).__name__}: {exc}"
        if not job.is_terminal:
            transition(job, JobState.ERROR, job.error)
        self._cleanup(job)

    @staticmethod
    def _cleanup(job: Job) -> None:
        """Remove uploaded media for jobs that ended in error/cancel."""
        if not job.uploaded or job.media_path is None:
            return
        try:
            Path(job.media_path).unlink(missing_ok=True)
        except OSError:  # pragma: no cover - best effort
            pass
