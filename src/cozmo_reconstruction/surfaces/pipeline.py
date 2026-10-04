"""Full upstream audit, independent evidence recomputation, atomic publication."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from cozmo_ingestion import CaptureReader, IngestionRequest
from cozmo_ingestion.bundle import BundleTransaction
from cozmo_ingestion.errors import require
from cozmo_ingestion.storage import BundleIntegrity, encoded, sha256, write_json
from cozmo_reconstruction.audit_numbers import equivalent
from cozmo_reconstruction.dense.pipeline import verify_dense

from .analysis import analyze
from .geometry import fit_planes
from .models import SurfacePolicy, SurfaceRequest
from .presentation import write_review

SCHEMA = "holo-surface-hypotheses-v1"
INPUT_POLICY = {
    "captured_depth": False,
    "grounding": False,
    "pose_refinement": False,
    "imu_integration": False,
    "semantic_confirmation": False,
    "boundary_filling": False,
}


def source_audit(request):
    verify_dense(request.dense, request.upstream)
    gravity = json.loads((request.upstream.bundle / "cameras.json").read_text())["wide"][
        "gravity_world"
    ]
    require(
        gravity == {"up": [0, 1, 0], "evidence": "EXPORTER_DECLARED"},
        "SURFACE_GRAVITY_UNSUPPORTED",
        "Require verified iOS source declaration; no inferred gravity",
    )


def guard_output(request):
    output = request.output.resolve()
    upstream = request.upstream
    raw = CaptureReader(upstream.bundle, "ios_preprocessing", upstream.source).roots["capture"]
    for folder in (raw, upstream.bundle, upstream.prepared, upstream.sparse, request.dense):
        folder = folder.resolve()
        require(
            not output.is_relative_to(folder) and not folder.is_relative_to(output),
            "OUTPUT_SOURCE_OVERLAP",
            str(output),
        )


class SurfacePipeline:
    def __init__(self, policy=None):
        self.policy = policy or SurfacePolicy()

    def run(self, request: SurfaceRequest):
        guard_output(request)
        require(not request.output.exists(), "OUTPUT_EXISTS", str(request.output))
        source_audit(request)
        identity = sha256(request.dense / "manifest.json")
        with np.load(request.dense / "cloud.npz") as cloud:
            planes = fit_planes(cloud["xyz_m"], self.policy)
        with BundleTransaction(
            IngestionRequest(request.dense.resolve(), request.output.resolve()),
            "surface-hypotheses",
        ) as tx:
            write_json(tx.stage / "policy.json", asdict(self.policy))
            write_json(tx.stage / "planes.json", planes.tolist())
            report = analyze(request.dense, planes, self.policy, stage=tx.stage)
            write_review(tx.stage, request.dense, report)
            fingerprint = {p.name: sha256(p) for p in sorted(Path(__file__).parent.glob("*.py"))}
            write_json(
                tx.stage / "manifest.json",
                {
                    "schema": SCHEMA,
                    "status": "SURFACE_HYPOTHESES_WITH_FINDINGS",
                    "dense_manifest_sha256": identity,
                    "policy": asdict(self.policy),
                    "input_policy": INPUT_POLICY,
                    "source_fingerprint": hashlib.sha256(encoded(fingerprint).encode()).hexdigest(),
                    "artifact_sha256": {
                        p.relative_to(tx.stage).as_posix(): sha256(p)
                        for p in sorted(tx.stage.rglob("*"))
                        if p.is_file()
                    },
                },
            )
            verification = verify_surfaces(tx.stage, request)
            tx.publish()
        return {
            "output": str(request.output),
            "planes": len(planes),
            "multiview_candidates": report["multiview_candidates"],
            "verification": verification,
        }


def verify_surfaces(output, request):
    source_audit(request)
    manifest = json.loads((output / "manifest.json").read_text())
    require(
        manifest["schema"] == SCHEMA
        and manifest["status"] == "SURFACE_HYPOTHESES_WITH_FINDINGS"
        and manifest["input_policy"] == INPUT_POLICY
        and manifest["dense_manifest_sha256"] == sha256(request.dense / "manifest.json"),
        "SURFACE_SOURCE_CHANGED",
        "Immutable dense provenance",
    )
    integrity = BundleIntegrity(output, manifest["artifact_sha256"])
    count = integrity.verify_all()
    policy = SurfacePolicy(**manifest["policy"])
    require(
        json.loads(integrity.path("policy.json").read_text()) == asdict(policy),
        "SURFACE_POLICY_CHANGED",
        "Policy",
    )
    planes = np.array(json.loads(integrity.path("planes.json").read_text())).reshape(-1, 4)
    with np.load(request.dense / "cloud.npz") as cloud:
        expected = fit_planes(cloud["xyz_m"], policy)
    require(
        planes.shape == expected.shape and np.allclose(planes, expected, atol=1e-10, rtol=1e-12),
        "SURFACE_PLANES_CHANGED",
        "Recomputed deterministic plane fitting",
    )
    report = analyze(request.dense, planes, policy, verify_samples=output)
    require(
        equivalent(json.loads(integrity.path("report.json").read_text()), report),
        "SURFACE_REPORT_CHANGED",
        "Recomputed source observations and occupied patches",
    )
    integrity.verify_all()
    return {
        "status": "VERIFIED",
        "artifacts": count,
        "physical_accuracy": "UNVERIFIED",
        "semantic_confirmation": False,
        "floorplan": "NOT_RUN",
    }
