"""Create immutable derived runs from existing verified captures."""

import json
import shutil
from pathlib import Path

from cozmo_ingestion import CaptureReader
from cozmo_ingestion.adapters.sensor_recorder import ADAPTER
from cozmo_ingestion.verification import verify

from .errors import WebError
from .reference_images import read_reference_image


def enqueue_preprocessing(
    repository, settings, parent_id: str, *, automatic_reconstruction=False
) -> dict:
    parent = repository.get(parent_id)
    if parent["state"] != "SUCCEEDED":
        raise WebError("RESULT_NOT_READY", "First finish capture validation", 409)
    folder = repository.folder(parent_id)
    reader = CaptureReader(folder / "bundle", source_root=folder / "raw")
    if reader.manifest["adapter"] != ADAPTER:
        raise WebError(
            "PREPROCESS_SOURCE_UNSUPPORTED",
            "Preprocessing currently supports Sensor Recorder iPhone captures",
            400,
        )
    # The isolated worker performs the full audit; request admission stays inexpensive.
    estimated = sum(
        p.stat().st_size
        for name in ("raw", "bundle", "annotations", "reference")
        for p in (folder / name).rglob("*")
        if p.is_file()
    )
    if shutil.disk_usage(settings.data_root).free < estimated * 4 + 128 * 1024**2:
        raise WebError("STORAGE_FULL", "Not enough storage for a separate preprocessing run", 507)
    job = repository.create(parent["label"][:100] + " · preprocessing", parent.get("reference"))
    return repository.update(
        job["id"],
        state="QUEUED",
        operation="PREPROCESS",
        parent_id=parent_id,
        reference_image=parent.get("reference_image"),
        automatic_reconstruction=automatic_reconstruction,
    )


def execute_preprocessing(folder: Path, settings, phase):
    from cozmo_preprocessing import PreprocessingPipeline, PreprocessingRequest
    from cozmo_preprocessing.media import FFmpegFrameDecoder
    from cozmo_preprocessing.verification import verify_preprocessing

    from .repository import JobRepository

    job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    repository = JobRepository(settings.data_root, settings.queue_limit)
    parent = repository.folder(job["parent_id"])
    if repository.get(job["parent_id"])["state"] != "SUCCEEDED":
        raise WebError("RESULT_NOT_READY", "Source capture is unavailable", 409)
    phase("VERIFYING")
    verify(parent / "bundle", parent / "raw")
    read_reference_image(parent)
    # Portable child captures own copies; deleting/retrying one run cannot break another.
    for name in ("raw", "bundle", "annotations", "reference"):
        source = parent / name
        if source.exists():
            if source.is_symlink() or any(p.is_symlink() for p in source.rglob("*")):
                raise WebError("SOURCE_CHANGED", "Capture storage has changed", 409)
            shutil.copytree(source, folder / name)
    phase("PREPROCESSING")
    report = PreprocessingPipeline(decoder=FFmpegFrameDecoder(settings.ffmpeg)).run(
        PreprocessingRequest(folder / "bundle", folder / "preprocessing", folder / "raw")
    )
    phase("VERIFYING")
    preprocessing_audit = verify_preprocessing(
        folder / "preprocessing", folder / "bundle", folder / "raw"
    )
    audit = verify(folder / "bundle", folder / "raw")
    result = json.loads((parent / "result.json").read_text(encoding="utf-8"))
    result.update(
        verification=audit, preprocessing=report, preprocessing_verification=preprocessing_audit
    )
    return result
