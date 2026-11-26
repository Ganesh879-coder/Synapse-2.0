"""Thread-safe Prometheus text-format operational metrics."""

from __future__ import annotations

import threading


class MetricsRegistry:
    """Tracks job counters and per-analyzer latency without storing PII."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.jobs_started = 0
        self.jobs_finished = 0
        self.jobs_failed = 0
        self._analyzer_sum: dict[str, float] = {}
        self._analyzer_count: dict[str, int] = {}

    def inc_started(self) -> None:
        with self._lock:
            self.jobs_started += 1

    def inc_finished(self) -> None:
        with self._lock:
            self.jobs_finished += 1

    def inc_failed(self) -> None:
        with self._lock:
            self.jobs_failed += 1

    def observe_analyzer(self, analyzer_name: str, duration_seconds: float) -> None:
        with self._lock:
            self._analyzer_sum[analyzer_name] = (
                self._analyzer_sum.get(analyzer_name, 0.0) + duration_seconds
            )
            self._analyzer_count[analyzer_name] = (
                self._analyzer_count.get(analyzer_name, 0) + 1
            )

    def render_prometheus(self, queue_depth: int) -> str:
        """Render metrics in Prometheus exposition text format."""
        with self._lock:
            lines = [
                "# TYPE kavach_jobs_started_total counter",
                f"kavach_jobs_started_total {self.jobs_started}",
                "# TYPE kavach_jobs_finished_total counter",
                f"kavach_jobs_finished_total {self.jobs_finished}",
                "# TYPE kavach_jobs_failed_total counter",
                f"kavach_jobs_failed_total {self.jobs_failed}",
                "# TYPE kavach_queue_depth gauge",
                f"kavach_queue_depth {queue_depth}",
                "# TYPE kavach_analyzer_duration_seconds_sum counter",
            ]
            for name, total_sec in sorted(self._analyzer_sum.items()):
                lines.append(
                    f'kavach_analyzer_duration_seconds_sum{{analyzer="{name}"}} {total_sec:.6f}'
                )
            lines.append("# TYPE kavach_analyzer_duration_seconds_count counter")
            for name, count in sorted(self._analyzer_count.items()):
                lines.append(
                    f'kavach_analyzer_duration_seconds_count{{analyzer="{name}"}} {count}'
                )
            return "\n".join(lines) + "\n"
