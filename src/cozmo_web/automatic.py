"""Bounded automatic orchestration; domain packages own geometry and audits."""

import importlib.util
import json
import shutil
from pathlib import Path

import numpy as np

from cozmo_ingestion.adapters.sensor_recorder import ADAPTER
from cozmo_ingestion.storage import BundleIntegrity, sha256, write_json
from cozmo_ingestion.verification import verify
from cozmo_preprocessing.verification import lines, verify_preprocessing

from .errors import WebError
from .reference_images import read_reference_image


def backend_available():
    return importlib.util.find_spec("pycolmap") is not None


def dense_available():
    from cozmo_reconstruction.dense.runtime import runtime_status

    return runtime_status()["available"]


def prepare_views(folder, settings, phase):
    from cozmo_preprocessing import PreprocessingPipeline, PreprocessingRequest
    from cozmo_preprocessing.media import FFmpegFrameDecoder

    phase("PREPROCESSING")
    report = PreprocessingPipeline(decoder=FFmpegFrameDecoder(settings.ffmpeg)).run(
        PreprocessingRequest(folder / "bundle", folder / "preprocessing", folder / "raw")
    )
    phase("VERIFYING")
    audit = verify_preprocessing(folder / "preprocessing", folder / "bundle", folder / "raw")
    return {"preprocessing": report, "preprocessing_verification": audit}


def dense_support_selection(sparse):
    """Prune views without two accepted-track neighbors; retain raw/prepared views."""
    from itertools import combinations

    manifest = json.loads((sparse / "manifest.json").read_text(encoding="utf-8"))
    integrity = BundleIntegrity(sparse, manifest["artifact_sha256"])
    mapping = json.loads(integrity.path("input_mapping.json").read_text(encoding="utf-8"))
    graph = {v["rank"]: set() for v in mapping}
    for point in lines(integrity.path("points.jsonl")):
        ranks = {o["rank"] for o in point["observations"]} & graph.keys()
        for first, second in combinations(ranks, 2):
            graph[first].add(second)
            graph[second].add(first)
    keep = set(graph)
    while True:
        remove = {rank for rank in keep if len(graph[rank] & keep) < 2}
        if not remove:
            break
        keep -= remove
    if len(keep) < 3:
        raise WebError(
            "DENSE_OVERLAP_INSUFFICIENT", "Need three views with mutual accepted-track support", 409
        )
    return tuple(sorted(keep)), sorted(graph.keys() - keep)


def reconstruct(folder, settings, phase):
    if not backend_available():
        raise WebError(
            "RECONSTRUCTION_BACKEND_MISSING",
            "Install the reconstruct extra and retry this prepared capture",
            503,
        )
    from cozmo_reconstruction import (
        ReconstructionPipeline,
        ReconstructionPolicy,
        ReconstructionRequest,
    )
    from cozmo_reconstruction.viewer.automatic import publish_sparse

    job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    mode = job.get("reconstruction_mode", settings.reconstruction_mode)
    use_dense = mode != "preview" and dense_available()
    if mode == "dense" and not use_dense:
        raise WebError(
            "DENSE_CUDA_UNAVAILABLE",
            "Dense reconstruction requires the GPU runtime and an available CUDA device. Prepared input is retained.",
            503,
        )

    phase("VERIFYING")
    verify_preprocessing(folder / "preprocessing", folder / "bundle", folder / "raw")
    manifest = json.loads((folder / "preprocessing/manifest.json").read_text(encoding="utf-8"))
    views = lines(
        BundleIntegrity(folder / "preprocessing", manifest["artifact_sha256"]).path("views.jsonl")
    )
    # Retain opening scene coverage; reference dimensions/detection are still excluded.
    eligible = [v["rank"] for v in views if v["tracking_state"] == "normal"]
    if len(eligible) < 3:
        raise WebError(
            "RECONSTRUCTION_SUPPORT_INSUFFICIENT",
            "Need at least three prepared views with normal tracking",
            409,
        )
    ranks = tuple(
        eligible[i] for i in np.linspace(0, len(eligible) - 1, min(100, len(eligible)), dtype=int)
    )
    phase("RECONSTRUCTING")
    request = ReconstructionRequest(
        folder / "preprocessing",
        folder / "bundle",
        folder / "reconstruction",
        folder / "raw",
        ranks,
    )
    ReconstructionPipeline(
        ReconstructionPolicy(
            max_views=100, timeout_seconds=min(900, max(1, settings.reconstruction_deadline - 120))
        )
    ).run(request)
    if use_dense:
        from cozmo_reconstruction.dense.models import DensePolicy, DenseRequest
        from cozmo_reconstruction.dense.pipeline import DensePipeline
        from cozmo_reconstruction.surfaces.models import SurfaceRequest
        from cozmo_reconstruction.surfaces.pipeline import SurfacePipeline
        from cozmo_reconstruction.viewer.dense_automatic import publish_dense

        if shutil.disk_usage(settings.data_root).free < 4 * 1024**3:
            raise WebError(
                "STORAGE_FULL", "Dense processing needs at least 4 GiB free working storage", 507
            )
        phase("DENSE_RECONSTRUCTING")
        dense_ranks, excluded = dense_support_selection(request.output)
        write_json(
            folder / "dense-selection.json",
            {
                "policy": "accepted-track graph 2-core; no temporal interval exclusion",
                "selected_ranks": dense_ranks,
                "excluded_ranks": excluded,
                "source_manifest_sha256": sha256(request.output / "manifest.json"),
            },
        )
        dense = DenseRequest(
            request.output,
            request.prepared,
            request.bundle,
            folder / "dense",
            request.source_root,
            dense_ranks,
        )
        DensePipeline(
            DensePolicy(timeout_seconds=min(1800, max(30, settings.reconstruction_deadline - 300)))
        ).run(dense)
        phase("EXTRACTING_SURFACES")
        surfaces = SurfaceRequest(dense, folder / "surfaces")
        SurfacePipeline().run(surfaces)
        phase("ESTIMATING_ROOM")
        published = publish_dense(surfaces, folder / "viewer", job["label"])
        published["dense_excluded_ranks"] = excluded
    else:
        phase("PUBLISHING")
        published = publish_sparse(request, folder / "viewer", job["label"])
        published["quality"] = "SPARSE_PREVIEW_ONLY"
    phase("PUBLISHING")
    result_id = "capture-" + folder.name
    root = settings.data_root / "reconstructions"
    root.mkdir(parents=True, exist_ok=True)
    from cozmo_ingestion.bundle import BundleTransaction
    from cozmo_ingestion.models import IngestionRequest

    # Atomic publication to writable storage; manually reviewed catalogs may be read-only.
    with BundleTransaction(IngestionRequest(folder / "viewer", root / result_id), "catalog") as tx:
        shutil.copytree(folder / "viewer", tx.stage, dirs_exist_ok=True)
        viewer = json.loads((tx.stage / "manifest.json").read_text(encoding="utf-8"))
        BundleIntegrity(tx.stage, viewer["artifact_sha256"]).verify_all()
        tx.publish()
    return {**published, "id": result_id, "opening_seconds_excluded": 0}


def enqueue_reconstruction(repository, settings, parent_id, mode="auto"):
    if mode not in {"auto", "dense", "preview"}:
        raise WebError("RECONSTRUCTION_MODE_INVALID", "Choose auto, dense or preview", 422)
    with repository.lock:
        parent = repository.get(parent_id)
        folder = repository.folder(parent_id)
        if (
            parent["state"] not in {"SUCCEEDED", "FAILED"}
            or not (folder / "preprocessing/manifest.json").is_file()
        ):
            raise WebError("RESULT_NOT_READY", "Finish preprocessing before reconstruction", 409)
        # An in-flight retry is idempotent, preventing duplicate work on repeated clicks.
        existing = next(
            (
                j
                for j in repository.list(None)
                if j.get("parent_id") == parent_id
                and j.get("operation") == "RECONSTRUCT"
                and j["state"] not in {"SUCCEEDED", "FAILED"}
            ),
            None,
        )
        if existing:
            return existing
        estimated = sum(
            p.stat().st_size
            for name in ("raw", "bundle", "preprocessing", "reference", "annotations")
            for p in (folder / name).rglob("*")
            if p.is_file()
        )
        if shutil.disk_usage(settings.data_root).free < estimated * 2 + 256 * 1024**2:
            raise WebError(
                "STORAGE_FULL", "Not enough storage for a separate reconstruction run", 507
            )
        job = repository.create(parent["label"][:95] + " · reconstruction", parent.get("reference"))
        return repository.update(
            job["id"],
            state="QUEUED",
            operation="RECONSTRUCT",
            parent_id=parent_id,
            reconstruction_mode=settings.reconstruction_mode if mode == "auto" else mode,
        )


def execute_retry(folder: Path, settings, phase):
    from .repository import JobRepository

    job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    repository = JobRepository(settings.data_root, settings.queue_limit)
    parent = repository.folder(job["parent_id"])
    phase("VERIFYING")
    verify(parent / "bundle", parent / "raw")
    verify_preprocessing(parent / "preprocessing", parent / "bundle", parent / "raw")
    read_reference_image(parent)
    for name in ("raw", "bundle", "preprocessing", "annotations", "reference"):
        source = parent / name
        if source.exists():
            if source.is_symlink() or any(p.is_symlink() for p in source.rglob("*")):
                raise WebError("SOURCE_CHANGED", "Capture storage has changed", 409)
            shutil.copytree(source, folder / name)
    result = json.loads((parent / "result.json").read_text(encoding="utf-8"))
    result.pop("reconstruction", None)
    write_json(folder / "verification.json", result["verification"])
    write_json(folder / "result.json", result)
    result["reconstruction"] = reconstruct(folder, settings, phase)
    return result


def finish_automatically(folder, settings, phase, result):
    if result["manifest"]["adapter"] != ADAPTER:
        result["automatic_reconstruction"] = {
            "status": "SKIPPED",
            "reason": "Automatic reconstruction currently supports verified Sensor Recorder ARKit exports",
        }
        return result
    result.update(prepare_views(folder, settings, phase))
    write_json(folder / "result.json", result)
    result["reconstruction"] = reconstruct(folder, settings, phase)
    result["automatic_reconstruction"] = {"status": "SUCCEEDED"}
    return result


def verify_automatic(folder):
    """Source-bound audit for downloadable results, including a failed later stage."""
    if not (folder / "reconstruction/manifest.json").is_file():
        return
    from cozmo_reconstruction.verification import verify_reconstruction

    verify_reconstruction(
        folder / "reconstruction", folder / "preprocessing", folder / "bundle", folder / "raw"
    )
    if (folder / "dense/manifest.json").is_file():
        from cozmo_reconstruction.dense.models import DenseRequest
        from cozmo_reconstruction.dense.pipeline import verify_dense
        from cozmo_reconstruction.surfaces.models import SurfaceRequest
        from cozmo_reconstruction.surfaces.pipeline import verify_surfaces

        dense = DenseRequest(
            folder / "reconstruction",
            folder / "preprocessing",
            folder / "bundle",
            folder / "dense",
            folder / "raw",
        )
        verify_dense(dense.output, dense)
        if (folder / "surfaces/manifest.json").is_file():
            verify_surfaces(folder / "surfaces", SurfaceRequest(dense, folder / "surfaces"))
    if (folder / "viewer/manifest.json").is_file():
        manifest = json.loads((folder / "viewer/manifest.json").read_text(encoding="utf-8"))
        sources = {"sparse": "reconstruction", "dense": "dense", "surfaces": "surfaces"}
        if any(
            name not in sources or digest != sha256(folder / sources[name] / "manifest.json")
            for name, digest in manifest["source_manifest_sha256"].items()
        ):
            raise WebError("SOURCE_CHANGED", "Reconstruction source has changed", 409)
        BundleIntegrity(folder / "viewer", manifest["artifact_sha256"]).verify_all()
