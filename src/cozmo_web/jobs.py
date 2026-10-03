"""Single bounded queue; HTTP handlers do not decode or reconstruct captures."""

import threading

from .repository import JobRepository
from .runner import ProcessRunner


class JobService:
    def __init__(self, repository: JobRepository, runner: ProcessRunner):
        self.repository, self.runner = repository, runner
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._work, name="capture-jobs", daemon=True)

    def start(self):
        self.repository.reconcile()
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=15)
        if self.thread.is_alive():
            raise RuntimeError("Worker did not stop; storage lock must remain held")

    def _work(self):
        while not self.stop.is_set():
            queued = [j for j in reversed(self.repository.list(None)) if j["state"] == "QUEUED"]
            if not queued:
                self.stop.wait(0.25)
                continue
            job = queued[0]
            try:
                self.repository.update(job["id"], state="VALIDATING_INPUT")
                self.runner.run(self.repository.folder(job["id"]), self.repository, self.stop)
            except Exception:
                self.repository.fail(
                    job["id"], "WORKER_FAILED", "Processing failed. Check storage and resubmit."
                )
