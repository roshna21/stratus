"""Long-running work, watched from a browser.

Building infrastructure takes minutes. An HTTP request that waits for it will
hit a timeout somewhere between the browser and the server, and even when it
does not, the page sits silent throughout — which is indistinguishable from
being broken. The command line solved this by streaming Terraform's output as
it arrived; a browser needs the same thing.

So an apply starts a job and returns immediately. The job runs on its own
thread, collecting output as it goes, and the page asks how it is doing.

Polling rather than a server-sent stream, deliberately. Terraform emits a line
every ten seconds, so a one-second poll is not far behind, and polling
survives a dropped connection, a sleeping laptop and a proxy that buffers —
all of which quietly break a long-lived stream. The failure mode of polling is
a late update; the failure mode of a broken stream is a page that looks
finished when it is not.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

JOB_TTL = timedelta(hours=1)
"""How long a finished job is kept so the page can read its result."""


@dataclass
class Job:
    id: str
    kind: str
    status: str = "running"
    """running | done | failed"""

    log: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    started: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished: datetime | None = None

    @property
    def expired(self) -> bool:
        end = self.finished or self.started
        return datetime.now(UTC) - end > JOB_TTL

    def snapshot(self, since: int = 0) -> dict[str, Any]:
        """State for the page, with only log lines it has not seen.

        Sending the whole log every second would grow quadratically over a
        build that produces hundreds of lines.
        """
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "log": self.log[since:],
            "log_length": len(self.log),
            "result": self.result,
            "error": self.error,
        }


class Jobs:
    """Somewhere to keep running work.

    In memory, which is the right scope for this: a job is only meaningful
    to the page that started it, and a restart means the browser is
    reconnecting to a server that is no longer doing the work anyway.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def start(self, kind: str, work: Callable[[Callable[[str], None]], dict[str, Any]]) -> Job:
        """Run `work` on a thread. It is handed a function to log progress."""
        job = Job(id=uuid.uuid4().hex[:12], kind=kind)

        with self._lock:
            self._sweep()
            self._jobs[job.id] = job

        def run() -> None:
            try:
                job.result = work(job.log.append)
                job.status = "done"
            except Exception as exc:  # noqa: BLE001 - reported to the page, not swallowed
                job.error = str(exc)
                job.status = "failed"
            finally:
                job.finished = datetime.now(UTC)

        # Daemon, so a job in flight cannot keep the process alive at
        # shutdown. Terraform's own state lock is what protects the work.
        threading.Thread(target=run, daemon=True, name=f"stratus-{kind}").start()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _sweep(self) -> None:
        for key in [k for k, v in self._jobs.items() if v.expired]:
            del self._jobs[key]
