"""Bounded worker pool with max queue length and graceful shutdown."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor


class QueueFullError(RuntimeError):
    """Raised when the bounded analysis queue is at capacity."""


class BoundedAnalysisPool:
    """Executes analysis jobs in a bounded ThreadPoolExecutor."""

    def __init__(self, max_workers: int = 2, max_queue_length: int = 16) -> None:
        self.max_workers = max(1, max_workers)
        self.max_queue_length = max(1, max_queue_length)
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers, thread_name_prefix="kavach-worker"
        )
        self._lock = threading.Lock()
        self._in_flight = 0

    @property
    def queue_depth(self) -> int:
        """Return current number of queued + active jobs."""
        with self._lock:
            return self._in_flight

    def submit(self, fn: Callable[..., None], *args: object, **kwargs: object) -> None:
        """Submit a job if queue capacity permits, otherwise raise QueueFullError."""
        with self._lock:
            if self._in_flight >= self.max_queue_length:
                raise QueueFullError(
                    "Analysis queue is currently full. Please retry in a moment."
                )
            self._in_flight += 1

        def _wrapped() -> None:
            try:
                fn(*args, **kwargs)
            finally:
                with self._lock:
                    self._in_flight = max(0, self._in_flight - 1)

        self._executor.submit(_wrapped)

    def shutdown(self, wait: bool = True) -> None:
        """Gracefully wait for in-flight jobs before exiting."""
        self._executor.shutdown(wait=wait)
