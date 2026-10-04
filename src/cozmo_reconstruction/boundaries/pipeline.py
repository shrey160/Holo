"""Full source audits, immutable region archive and atomic partial evidence publication."""

import hashlib
import shutil
from dataclasses import asdict
from pathlib import Path

import numpy as np

from cozmo_ingestion import CaptureReader, IngestionRequest
from cozmo_ingestion.bundle import BundleTransaction
from cozmo_ingestion.errors import require
from cozmo_ingestion.storage import encoded, sha256, write_json

from .analysis import analyze
from .models import BoundaryPolicy
from .presentation import write_review
from .reviews import inputs, load_review, source_audit, template

SCHEMA = "holo-partial-boundaries-v1"
INPUT_POLICY = {
    "captured_depth": False,
    "grounding_geometry": False,
    "pose_refinement": False,
    "scale_correction": False,
    "whole_plane_semantic_promotion": False,
    "boundary_filling": False,
    "orthogonal_snapping": False,
}


def guard_output(request):
    output = request.output.resolve()
    surface = request.surfaces
    upstream = surface.upstream
    raw = CaptureReader(upstream.bundle, "ios_preprocessing", upstream.source).roots["capture"]
    for path in (
        raw,
        upstream.bundle,
        upstream.prepared,
        upstream.sparse,
        upstream.output,
        surface.output,
        request.review,
        request.grounding,
    ):
        if path is not None:
            path = path.resolve()
            require(
                not output.is_relative_to(path) and not path.is_relative_to(output),
                "OUTPUT_SOURCE_OVERLAP",
                str(output),
            )


class BoundaryPipeline:
    def __init__(self, policy=None):
        self.policy = policy or BoundaryPolicy()

    def run(self, request):
        from .verification import verify_boundaries

        guard_output(request)
        require(not request.output.exists(), "OUTPUT_EXISTS", str(request.output))
        source_audit(request)
        identity, plane_report, views = inputs(request)
        review_sha = sha256(request.review) if request.review else None
        review = (
            load_review(request.review, identity, plane_report["planes"], views)
            if request.review
            else template(identity)
        )
        with BundleTransaction(
            IngestionRequest(request.surfaces.output.resolve(), request.output.resolve()),
            "partial-boundaries",
        ) as tx:
            write_json(tx.stage / "review.json", review)
            if request.review:
                shutil.copyfile(request.review, tx.stage / "review_input.json")
            write_json(tx.stage / "views.json", views)
            write_json(tx.stage / "policy.json", asdict(self.policy))
            report, arrays = analyze(request, review, plane_report, self.policy)
            write_json(tx.stage / "report.json", report)
            np.savez_compressed(tx.stage / "reviewed_observations.npz", **arrays)
            write_review(tx.stage, request, views, review, report, arrays, self.policy)
            require(
                request.review is None or sha256(request.review) == review_sha,
                "BOUNDARY_REVIEW_SOURCE_CHANGED",
                "Review changed during processing",
            )
            fingerprint = {
                p.name: hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest()
                for p in sorted(Path(__file__).parent.glob("*.py"))
            }
            write_json(
                tx.stage / "manifest.json",
                {
                    "schema": SCHEMA,
                    "status": "PARTIAL_BOUNDARIES_WITH_FINDINGS",
                    "identity": identity,
                    "input_policy": INPUT_POLICY,
                    "policy": asdict(self.policy),
                    "review_input_sha256": review_sha,
                    "source_fingerprint": hashlib.sha256(encoded(fingerprint).encode()).hexdigest(),
                    "artifact_sha256": {
                        p.relative_to(tx.stage).as_posix(): sha256(p)
                        for p in sorted(tx.stage.rglob("*"))
                        if p.is_file()
                    },
                },
            )
            verification = verify_boundaries(tx.stage, request)
            tx.publish()
        return {
            "output": str(request.output),
            "status": report["status"],
            "supported_segments": report["supported_segments"],
            "verification": verification,
        }
