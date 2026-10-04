"""Audit-bound dense coordinator with timeout-isolated worker and atomic publication."""

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

from cozmo_ingestion import CaptureReader, IngestionRequest
from cozmo_ingestion.bundle import BundleTransaction
from cozmo_ingestion.errors import require
from cozmo_ingestion.storage import BundleIntegrity, encoded, sha256, write_json
from cozmo_preprocessing.verification import lines
from cozmo_reconstruction.audit_numbers import equivalent
from cozmo_reconstruction.verification import verify_reconstruction

from .analysis import analyze
from .geometry import neighbors
from .models import DensePolicy, DenseRequest

SCHEMA = "holo-fixed-pose-dense-v1"
INPUT_POLICY = {
    "geometry": ["RGB", "intrinsics", "fixed ARKit poses"],
    "captured_depth": False,
    "grounding": False,
    "imu_integration": False,
    "pose_refinement": False,
}


def audit_source(request):
    return verify_reconstruction(request.sparse, request.prepared, request.bundle, request.source)


def selection(request):
    mapping = json.loads((request.sparse / "input_mapping.json").read_text())
    ranks = (
        request.ranks if request.ranks is not None else tuple(sorted(v["rank"] for v in mapping))
    )
    require(
        3 <= len(ranks) <= 100
        and tuple(sorted(set(ranks))) == ranks
        and all(type(r) is int for r in ranks)
        and set(ranks).issubset(v["rank"] for v in mapping),
        "DENSE_SELECTION_INVALID",
        "3..100 unique ascending verified sparse ranks",
    )
    return [v for v in mapping if v["rank"] in ranks]


def backend(stage, sparse, policy):
    environment = dict(
        os.environ, OMP_NUM_THREADS=str(policy.threads), OPENBLAS_NUM_THREADS=str(policy.threads)
    )
    with (stage / "backend.log").open("w", encoding="utf-8") as log:
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "cozmo_reconstruction.dense.worker",
                    str(stage),
                    str(sparse),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                env=environment,
            )
            try:
                process.wait(timeout=policy.timeout_seconds)
            except subprocess.TimeoutExpired:
                # The native worker can own a CUDA executable: kill its whole Windows tree.
                if os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                    )
                else:
                    process.kill()
                process.wait(timeout=10)
                raise
        except subprocess.TimeoutExpired as error:
            raise ValueError(
                f"Dense worker exceeded {policy.timeout_seconds}s; see backend.log"
            ) from error
    require(
        process.returncode == 0,
        "DENSE_BACKEND_FAILED",
        f"Exit {process.returncode}; see {stage / 'backend.log'}",
    )


class DensePipeline:
    def __init__(self, policy=None, worker=backend):
        self.policy = policy or DensePolicy()
        self.worker = worker

    def run(self, request: DenseRequest):
        audit_source(request)
        mapping = selection(request)
        identity = sha256(request.sparse / "manifest.json")
        output = request.output.resolve()
        raw_root = CaptureReader(request.bundle, "ios_preprocessing", request.source).roots[
            "capture"
        ]
        for source in (request.sparse, request.prepared, request.bundle, raw_root):
            if source is not None:
                require(
                    not output.is_relative_to(source.resolve())
                    and not source.resolve().is_relative_to(output),
                    "OUTPUT_SOURCE_OVERLAP",
                    str(output),
                )
        points = lines(request.sparse / "points.jsonl")
        schedule = neighbors(
            points, {v["rank"]: v["image"] for v in mapping}, self.policy.neighbors
        )
        with BundleTransaction(
            IngestionRequest(request.sparse.resolve(), output), "fixed-pose-dense"
        ) as tx:
            stage = tx.stage
            write_json(stage / "policy.json", asdict(self.policy))
            write_json(stage / "input_mapping.json", mapping)
            write_json(stage / "neighbors.json", schedule)
            print(f"Dense {len(mapping)} views; backend log: {stage / 'backend.log'}", flush=True)
            self.worker(stage, request.sparse.resolve(), self.policy)
            report = analyze(stage, self.policy, points)
            write_json(stage / "report.json", report)
            audit_source(request)
            require(
                sha256(request.sparse / "manifest.json") == identity,
                "DENSE_SOURCE_CHANGED",
                "Sparse manifest",
            )
            fingerprint = {
                p.name: hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest()
                for p in sorted(Path(__file__).parent.glob("*.py"))
            }
            write_json(
                stage / "manifest.json",
                {
                    "schema": SCHEMA,
                    "status": "DENSE_WITH_FINDINGS",
                    "sparse_manifest_sha256": identity,
                    "policy": asdict(self.policy),
                    "source_fingerprint": hashlib.sha256(encoded(fingerprint).encode()).hexdigest(),
                    "input_policy": INPUT_POLICY,
                    "artifact_sha256": {
                        p.relative_to(stage).as_posix(): sha256(p)
                        for p in sorted(stage.rglob("*"))
                        if p.is_file()
                    },
                },
            )
            verification = verify_dense(stage, request)
            tx.publish()
        return {"output": str(output), "report": report, "verification": verification}


def verify_dense(output: Path, request: DenseRequest):
    audit_source(request)
    manifest = json.loads((output / "manifest.json").read_text())
    require(
        manifest["schema"] == SCHEMA
        and manifest["input_policy"] == INPUT_POLICY
        and manifest["status"] == "DENSE_WITH_FINDINGS"
        and manifest["sparse_manifest_sha256"] == sha256(request.sparse / "manifest.json"),
        "DENSE_SOURCE_CHANGED",
        "Manifest identity",
    )
    integrity = BundleIntegrity(output, manifest["artifact_sha256"])
    count = integrity.verify_all()
    runtime = json.loads(integrity.path("backend.json").read_text())
    require(
        runtime["name"] == "COLMAP CUDA PatchMatch"
        and runtime["version"] == "4.2.1"
        and runtime["has_cuda"] is True
        and runtime["depth_source"] == "RGB multi-view stereo"
        and runtime["depth_convention"] == "optical camera Z",
        "DENSE_BACKEND_CHANGED",
        "Pinned RGB stereo provenance",
    )
    policy = DensePolicy(**manifest["policy"])
    require(
        json.loads(integrity.path("policy.json").read_text()) == asdict(policy),
        "DENSE_POLICY_CHANGED",
        "Policy",
    )
    mapping = json.loads(integrity.path("input_mapping.json").read_text())
    bound = DenseRequest(
        request.sparse,
        request.prepared,
        request.bundle,
        output,
        request.source,
        tuple(sorted(v["rank"] for v in mapping)),
    )
    require(mapping == selection(bound), "DENSE_SOURCE_CHANGED", "Image/calibration/pose mapping")
    points = lines(request.sparse / "points.jsonl")
    require(
        json.loads(integrity.path("neighbors.json").read_text())
        == neighbors(points, {v["rank"]: v["image"] for v in mapping}, policy.neighbors),
        "DENSE_NEIGHBORS_CHANGED",
        "Sparse co-visibility",
    )
    originals = {c["image"]: c for c in json.loads((request.sparse / "cameras.json").read_text())}
    cameras = json.loads(integrity.path("cameras.json").read_text())
    import pycolmap as pc

    from cozmo_reconstruction.colmap import camera_records

    model = pc.Reconstruction(integrity.path("workspace/sparse/cameras.bin").parent)
    all_mapping = json.loads((request.sparse / "input_mapping.json").read_text())
    actual = {c["image"]: c for c in camera_records(model, {v["image"]: v for v in all_mapping})}
    require(
        len(cameras) == len(mapping)
        and {c["image"] for c in cameras} == {v["image"] for v in mapping},
        "DENSE_CAMERA_IDENTITY",
        "Count/names",
    )
    for c in cameras:
        require(
            all(equivalent(c[k], value) for k, value in actual[c["image"]].items()),
            "DENSE_MODEL_CHANGED",
            c["image"],
        )
        before = originals[c["image"]]
        scale = np.array(c["image_size"]) / before["image_size"]
        require(
            c["rank"] == before["rank"]
            and c["model"] == "PINHOLE"
            and max(c["image_size"]) <= policy.max_image_size
            and np.allclose(c["camera_from_world"], before["camera_from_world"], atol=1e-10, rtol=0)
            and np.allclose(c["center_m"], before["center_m"], atol=1e-10, rtol=0)
            and np.allclose(
                c["params"], np.array(before["params"]) * scale[[0, 1, 0, 1]], atol=1e-8, rtol=0
            ),
            "DENSE_CAMERA_CHANGED",
            c["image"],
        )
    expected = analyze(output, policy, points, write=False)
    require(
        equivalent(json.loads(integrity.path("report.json").read_text()), expected),
        "DENSE_REPORT_CHANGED",
        "Recomputed depth masks/cloud/report",
    )
    integrity.verify_all()
    return {
        "status": "VERIFIED",
        "artifacts": count,
        "source_gauge_preserved": True,
        "physical_accuracy": "UNVERIFIED",
    }
