"""Publish a separate appearance result without editing the structural viewer."""

import json
import shutil
from pathlib import Path

import numpy as np

from cozmo_ingestion.bundle import BundleTransaction
from cozmo_ingestion.errors import require
from cozmo_ingestion.models import IngestionRequest
from cozmo_ingestion.storage import BundleIntegrity, sha256, write_json

from .format import encode_splats


def verified(root):
    manifest = json.loads((root / "manifest.json").read_text())
    integrity = BundleIntegrity(root, manifest["artifact_sha256"])
    integrity.verify_all()
    return manifest, integrity


def publish(inputs: Path, trial: Path, viewer: Path, output: Path):
    inputs, trial, viewer, output = (p.resolve() for p in (inputs, trial, viewer, output))
    for source in (inputs, trial, viewer):
        require(
            not output.is_relative_to(source) and not source.is_relative_to(output),
            "OUTPUT_SOURCE_OVERLAP",
            str(output),
        )
    manifests, integrities = zip(*(verified(root) for root in (inputs, trial, viewer)), strict=True)
    require(
        [m["schema"] for m in manifests]
        == ["holo-gsplat-inputs-v1", "holo-gsplat-trial-v1", "holo-reconstruction-viewer-v1"],
        "GAUSSIAN_INPUT",
        "Unsupported schema",
    )
    report = json.loads(integrities[1].path("report.json").read_text())
    require(
        report["status"] == "EXPERIMENT_COMPLETE"
        and not report["pose_optimization"]
        and not report["scale_normalization"],
        "GAUSSIAN_INPUT",
        "Fixed-camera trial required",
    )
    require(
        report["inputs_manifest_sha256"] == sha256(inputs / "manifest.json"),
        "GAUSSIAN_INPUT",
        "Training inputs differ",
    )
    require(
        manifests[0]["dense_manifest_sha256"] == manifests[2]["source_manifest_sha256"]["dense"]
        and manifests[0]["boundary_manifest_sha256"]
        == manifests[2]["source_manifest_sha256"]["boundaries"],
        "GAUSSIAN_INPUT",
        "Viewer and experiment have different source geometry",
    )
    initial = np.mean([r["psnr_db"] for r in report["initial"]])
    final = np.mean([r["psnr_db"] for r in report["final"]])
    require(
        np.isfinite(initial) and np.isfinite(final) and final > initial + 1,
        "GAUSSIAN_QUALITY",
        "Photometric holdout improvement must exceed 1 dB",
    )
    scene = json.loads(integrities[2].path("scene.json").read_text())
    swap = np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, -1, 0, 0], [0, 0, 0, 1]])
    transform = swap @ np.asarray(scene["source_floor_frame"]["floor_from_world"])
    identities = [sha256(root / "manifest.json") for root in (inputs, trial, viewer)]
    with np.load(integrities[1].path("gaussians.npz"), allow_pickle=False) as data:
        packed, positions = encode_splats(data, transform)
    require(
        len(positions) == report["gaussians"] and 1000 <= len(positions) <= 200000,
        "GAUSSIAN_INPUT",
        "Count mismatch/limit",
    )
    with BundleTransaction(IngestionRequest(trial, output), "gaussian-viewer") as tx:
        (tx.stage / "room.splat").write_bytes(packed)
        shutil.copyfile(integrities[1].path("report.json"), tx.stage / "report.json")
        for name in ("initial", "final"):
            row = report[name][len(report[name]) // 2]
            shutil.copyfile(
                integrities[1].path(f"{name}-{row['rank']:06d}.jpg"), tx.stage / f"{name}.jpg"
            )
        with np.load(integrities[0].path("inputs.npz"), allow_pickle=False) as prepared:
            pose = np.linalg.inv(prepared["viewmats"][len(prepared["viewmats"]) // 2])
        camera = transform[:3, :3] @ pose[:3, 3] + transform[:3, 3]
        direction = transform[:3, :3] @ pose[:3, 2]
        write_json(
            tx.stage / "scene.json",
            {
                "label": scene["label"],
                "reconstruction_id": viewer.name,
                "gaussians": len(positions),
                "units": "source estimated metres",
                "physical_accuracy": "UNVERIFIED",
                "viewer_manifest_sha256": identities[2],
                "coordinates": scene["coordinates"],
                "display_from_world": transform.tolist(),
                "bounds": [positions.min(axis=0).tolist(), positions.max(axis=0).tolist()],
                "camera_position": camera.tolist(),
                "camera_target": (camera + 2 * direction).tolist(),
                "validation_scope": report["validation_scope"],
                "initial_psnr_db": float(initial),
                "final_psnr_db": float(final),
                "scope": "Trained appearance; no structural boundary or dimension correction",
            },
        )
        for root, identity, integrity in zip(
            (inputs, trial, viewer), identities, integrities, strict=True
        ):
            require(sha256(root / "manifest.json") == identity, "SOURCE_CHANGED", str(root))
            integrity.verify_all()
        hashes = {p.name: sha256(p) for p in tx.stage.iterdir() if p.is_file()}
        write_json(
            tx.stage / "manifest.json",
            {
                "schema": "holo-gaussian-viewer-v1",
                "source_manifest_sha256": dict(
                    zip(("inputs", "trial", "viewer"), identities, strict=True)
                ),
                "artifact_sha256": hashes,
            },
        )
        BundleIntegrity(tx.stage, hashes).verify_all()
        tx.publish()
    return {
        "status": "PUBLISHED",
        "gaussians": len(positions),
        "initial_psnr_db": float(initial),
        "final_psnr_db": float(final),
    }
