"""Atomic local job records and an OS-released single-instance storage lock."""

import json
import os
import re
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .errors import WebError

TERMINAL = {"SUCCEEDED", "FAILED"}


def now() -> str:
    return datetime.now(UTC).isoformat()


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


class DataLock:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.stream = (root / ".server.lock").open("a+b")
        if self.stream.tell() == 0:
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.stream.close()
            raise RuntimeError("Another server already owns DATA_ROOT") from error

    def close(self):
        self.stream.close()


class JobRepository:
    def __init__(self, root: Path, queue_limit: int):
        self.root = root.resolve() / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.queue_limit = queue_limit
        self.lock = threading.RLock()

    def folder(self, job_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise WebError("JOB_NOT_FOUND", "Capture job not found", 404)
        return self.root / job_id

    def get(self, job_id: str) -> dict:
        with self.lock:
            path = self.folder(job_id) / "job.json"
            if not path.is_file():
                raise WebError("JOB_NOT_FOUND", "Capture job not found", 404)
            return json.loads(path.read_text(encoding="utf-8"))

    def list(self, limit: int | None = 50) -> list[dict]:
        with self.lock:
            jobs = [json.loads(p.read_text(encoding="utf-8")) for p in self.root.glob("*/job.json")]
            jobs.sort(key=lambda j: j["created_at"], reverse=True)
            return jobs[:limit] if limit else jobs

    def create(self, label: str, reference: dict | None, modality: str = "video") -> dict:
        with self.lock:
            pending = sum(j["state"] not in TERMINAL for j in self.list(None))
            if pending >= self.queue_limit + 1:
                raise WebError("QUEUE_FULL", "Processing queue is full. Try again shortly.", 429)
            job_id = uuid.uuid4().hex
            folder = self.folder(job_id)
            folder.mkdir()
            (folder / "incoming").mkdir()
            job = {
                "id": job_id,
                "label": label or "Untitled capture",
                "state": "RECEIVING",
                "created_at": now(),
                "updated_at": now(),
                "modality": modality,
                "reference": reference,
                "summary": None,
                "error": None,
            }
            atomic_json(folder / "job.json", job)
            return job

    def update(self, job_id: str, **changes) -> dict:
        with self.lock:
            job = self.get(job_id)
            job.update(changes, updated_at=now())
            atomic_json(self.folder(job_id) / "job.json", job)
            return job

    def fail(self, job_id: str, code: str, message: str):
        changes = {"failed_stage": self.get(job_id)["state"]}
        result = self.folder(job_id) / "result.json"
        if result.is_file():
            try:
                changes["summary"] = summarize(json.loads(result.read_text(encoding="utf-8")))
            except (OSError, ValueError, KeyError, TypeError):
                # A broken result must not prevent persisting failure or stop the queue.
                pass
        return self.update(
            job_id, state="FAILED", error={"code": code, "message": message}, **changes
        )

    def reconcile(self):
        for job in self.list(None):
            if job["state"] not in TERMINAL | {"QUEUED"}:
                self.fail(job["id"], "INTERRUPTED", "Processing was interrupted. Submit a new run.")


def summarize(result):
    manifest, report = result["manifest"], result["validation"]
    if manifest.get("schema") == "canonical-capture-2":
        return {
            "modality": manifest.get("mode"),
            "room_count": manifest["room_count"],
            "image_count": manifest["image_count"],
            "distinct_image_count": manifest["distinct_image_count"],
            "profile": manifest.get("profile"),
            "capabilities": manifest["capabilities"],
            "findings": report["findings"],
            "independent_accuracy": report.get("independent_accuracy"),
            "verification": result["verification"],
        }
    return {
        "frame_count": manifest["frame_count"],
        "capabilities": manifest["capabilities"],
        "tracking_states": report["tracking_states"],
        "findings": report["findings"],
        "independent_accuracy": report["independent_accuracy"],
        "grounding": manifest["capabilities"]["grounding_object"],
        "verification": result["verification"],
        "preprocessing": result.get("preprocessing"),
        "preprocessing_verification": result.get("preprocessing_verification"),
        "reconstruction": result.get("reconstruction"),
        "automatic_reconstruction": result.get("automatic_reconstruction"),
    }
