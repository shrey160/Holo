"""Bounded subprocess runner with process-tree cleanup on both supported hosts."""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from .config import Settings
from .repository import JobRepository, summarize


def terminate_tree(process: subprocess.Popen):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=10)


class ProcessRunner:
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, folder: Path, repository: JobRepository, stop: threading.Event):
        env = dict(os.environ)
        env.update(
            DATA_ROOT=str(self.settings.data_root.resolve()),
            RECONSTRUCTION_TIMEOUT_SECONDS=str(self.settings.reconstruction_deadline),
            RECONSTRUCTION_MODE=self.settings.reconstruction_mode,
            MAX_EXPANDED_BYTES=str(self.settings.expanded_limit),
            MAX_ARCHIVE_MEMBERS=str(self.settings.member_limit),
        )
        if self.settings.ffmpeg:
            env["FFMPEG_PATH"] = self.settings.ffmpeg
        options = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if os.name == "nt"
            else {"start_new_session": True}
        )
        logs = folder / "logs"
        logs.mkdir(exist_ok=True)
        job = repository.get(folder.name)
        deadline = (
            self.settings.reconstruction_deadline
            if job.get("automatic_reconstruction") or job.get("operation") == "RECONSTRUCT"
            else self.settings.deadline
        )
        with (logs / "worker.log").open("wb") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "cozmo_web.worker", str(folder)],
                stdout=log,
                stderr=log,
                env=env,
                **options,
            )
            started, state = time.monotonic(), None
            try:
                while process.poll() is None:
                    if stop.is_set() or time.monotonic() - started > deadline:
                        terminate_tree(process)
                        code = "INTERRUPTED" if stop.is_set() else "JOB_TIMEOUT"
                        repository.fail(
                            folder.name, code, "Run interrupted or timed out. Submit a new run."
                        )
                        return
                    phase_file = folder / "phase.json"
                    if phase_file.is_file():
                        phase = json.loads(phase_file.read_text(encoding="utf-8"))["state"]
                        if phase != state and phase != "SUCCEEDED":
                            from .repository import now

                            history = repository.get(folder.name).get("stage_history", [])
                            repository.update(
                                folder.name,
                                state=phase,
                                stage_history=[*history, {"stage": phase, "started_at": now()}],
                            )
                            state = phase
                    stop.wait(0.15)
            finally:
                terminate_tree(process)
        if process.returncode != 0:
            error_file = folder / "error.json"
            error = (
                json.loads(error_file.read_text(encoding="utf-8"))
                if error_file.is_file()
                else {
                    "code": "WORKER_FAILED",
                    "message": "Worker failed. Resubmit the original export.",
                }
            )
            repository.fail(folder.name, **error)
            return
        result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        repository.update(
            folder.name,
            state="SUCCEEDED",
            reference_image=result.get("reference_image"),
            summary=summarize(result),
        )
