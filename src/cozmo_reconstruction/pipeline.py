"""Source-bound application coordinator and atomic derived publication."""

import hashlib
import json
import platform
import shutil
from dataclasses import asdict
from pathlib import Path

from cozmo_ingestion import IngestionRequest
from cozmo_ingestion.bundle import BundleTransaction
from cozmo_ingestion.errors import require
from cozmo_ingestion.storage import encoded, sha256, write_json
from cozmo_preprocessing.verification import lines

from .analysis import analyze
from .backend import PyCOLMAPBackend
from .cameras import select_pairs
from .inputs import PreparedInput
from .models import ReconstructionPolicy, ReconstructionRequest
from .ports import ReconstructionBackend
from .preview import write_preview

SCHEMA = "holo-fixed-pose-sparse-v1"
INPUT_POLICY = {
    "geometry": [
        "selected RGB",
        "per-frame intrinsics",
        "source ARKit optical camera-to-world poses",
    ],
    "diagnostic_only": ["preprocessing flags", "native gyro interval statistics"],
    "excluded": [
        "capture depth",
        "capture confidence",
        "grounding dimensions",
        "reference photo",
        "evaluation geometry",
        "magnetometer",
        "fused device motion",
    ],
    "grounding_applied": False,
    "scale_correction": False,
    "pose_refinement": False,
    "imu_integration": False,
}


class ReconstructionPipeline:
    def __init__(
        self,
        policy: ReconstructionPolicy | None = None,
        backend: ReconstructionBackend | None = None,
    ):
        self.policy = policy or ReconstructionPolicy()
        self.backend = backend or PyCOLMAPBackend()

    def run(self, request: ReconstructionRequest) -> dict:
        data = PreparedInput(request, self.policy)
        output = request.output.resolve()
        for source in (data.source, data.bundle, data.prepared):
            require(
                not output.is_relative_to(source) and not source.is_relative_to(output),
                "OUTPUT_SOURCE_OVERLAP",
                str(output),
            )
        with BundleTransaction(IngestionRequest(data.prepared, output), "fixed-pose-sparse") as tx:
            stage = tx.stage
            (stage / "images").mkdir()
            for view in data.mapping:
                shutil.copyfile(
                    data.integrity.path(view["prepared_image"]), stage / "images" / view["image"]
                )
            write_json(stage / "input_mapping.json", data.mapping)
            write_json(stage / "policy.json", asdict(self.policy))
            pairs = select_pairs(data.mapping, self.policy)
            (stage / "pairs.txt").write_text(
                "".join(f"{a} {b}\n" for a, b in pairs), encoding="utf-8", newline="\n"
            )
            print(
                f"Reconstruct {len(data.mapping)} views / {len(pairs)} pairs; backend log: {stage / 'backend.log'}",
                flush=True,
            )
            self.backend.run(stage, self.policy)
            cameras = json.loads((stage / "cameras.json").read_text(encoding="utf-8"))
            points, candidates = (
                lines(stage / "points.jsonl"),
                lines(stage / "candidate_points.jsonl"),
            )
            report = analyze(data.mapping, points, candidates, cameras, self.policy)
            report["excluded_prepared_ranks"] = sorted(
                set(data.all_ranks) - {v["rank"] for v in data.mapping}
            )
            report["pair_candidates"] = len(pairs)
            write_json(stage / "report.json", report)
            write_preview(stage / "preview.svg", data.mapping, points, report)
            data.recheck()
            root = Path(__file__).parent
            fingerprint = {
                p.name: hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest()
                for p in sorted(root.glob("*.py"))
            }
            write_json(
                stage / "manifest.json",
                {
                    "schema": SCHEMA,
                    "status": "SPARSE_RECONSTRUCTED_WITH_FINDINGS",
                    "input_policy": INPUT_POLICY,
                    "source_identity": data.snapshot,
                    "policy": asdict(self.policy),
                    "python": platform.python_version(),
                    "source_fingerprint": hashlib.sha256(encoded(fingerprint).encode()).hexdigest(),
                    "artifact_sha256": {
                        p.relative_to(stage).as_posix(): sha256(p)
                        for p in sorted(stage.rglob("*"))
                        if p.is_file()
                    },
                },
            )
            from .verification import verify_reconstruction

            audit = verify_reconstruction(
                stage, request.prepared, request.bundle, request.source_root
            )
            tx.publish()
        return {"output": str(output), "report": report, "verification": audit}
