"""Immutable source bindings and transactional diagnostic publication."""

import hashlib
import shutil
from dataclasses import asdict
from pathlib import Path

from cozmo_ingestion import CaptureReader, IngestionRequest
from cozmo_ingestion.bundle import BundleTransaction
from cozmo_ingestion.errors import require
from cozmo_ingestion.storage import encoded, sha256, write_json

from .analysis import analyze
from .annotations import audit_source, inputs, load_annotations, template
from .confirmation import load_confirmation
from .models import GroundingPolicy
from .presentation import write_review

SCHEMA = "holo-grounding-diagnostic-v1"
REVIEW_SCHEMA = "holo-grounding-diagnostic-v2"
INPUT_POLICY = {
    "geometry": ["RGB corners", "intrinsics", "fixed ARKit poses", "declared reference size"],
    "captured_depth": False,
    "pose_refinement": False,
    "imu_integration": False,
    "scale_correction": False,
    "semantic_confirmation": False,
}


def guard_output(request):
    output = request.output.resolve()
    raw = CaptureReader(request.bundle, "ios_assisted_rgb", request.source).roots["capture"]
    for path in (
        raw,
        request.prepared,
        request.bundle,
        request.sparse,
        request.dense,
        request.surfaces,
        request.annotations,
        request.review_confirmation,
    ):
        if path is not None:
            path = path.resolve()
            require(
                not output.is_relative_to(path) and not path.is_relative_to(output),
                "OUTPUT_SOURCE_OVERLAP",
                str(output),
            )


class GroundingPipeline:
    def __init__(self, policy=None):
        self.policy = policy or GroundingPolicy()

    def run(self, request):
        from .verification import verify_grounding

        guard_output(request)
        require(not request.output.exists(), "OUTPUT_EXISTS", str(request.output))
        reader = audit_source(request)
        identity, reference, views = inputs(request, reader)
        if request.annotations:
            annotations = load_annotations(request.annotations, identity, request.object_id, views)
            annotation_identity = sha256(request.annotations)
        else:
            annotations = template(identity, request.object_id)
            annotations["annotator"] = "UNANNOTATED"
            annotation_identity = None
        confirmation = None
        confirmation_identity = None
        if request.review_confirmation:
            require(
                request.annotations is not None,
                "GROUNDING_REVIEW_INVALID",
                "Review requires original annotations",
            )
            confirmation_identity = sha256(request.review_confirmation)
            confirmation = load_confirmation(
                request.review_confirmation, annotation_identity, identity, annotations
            )
        with BundleTransaction(
            IngestionRequest(request.prepared.resolve(), request.output.resolve()),
            "grounding-diagnostic",
        ) as tx:
            write_json(tx.stage / "annotations.json", annotations)
            if request.annotations:
                shutil.copyfile(request.annotations, tx.stage / "annotation_source.json")
            if request.review_confirmation:
                shutil.copyfile(request.review_confirmation, tx.stage / "review_confirmation.json")
            write_json(tx.stage / "views.json", views)
            write_json(tx.stage / "reference.json", reference)
            write_json(tx.stage / "policy.json", asdict(self.policy))
            report = analyze(views, reference, annotations, self.policy, request, confirmation)
            write_json(tx.stage / "report.json", report)
            write_review(
                tx.stage, request.prepared, identity, request.object_id, views, annotations, report
            )
            if request.annotations:
                require(
                    sha256(request.annotations) == annotation_identity,
                    "GROUNDING_ANNOTATION_SOURCE_CHANGED",
                    "Input changed during diagnostic",
                )
            if request.review_confirmation:
                require(
                    sha256(request.review_confirmation) == confirmation_identity,
                    "GROUNDING_REVIEW_SOURCE_CHANGED",
                    "Review changed during diagnostic",
                )
            fingerprint = {
                p.name: hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest()
                for p in sorted(Path(__file__).parent.glob("*.py"))
            }
            write_json(
                tx.stage / "manifest.json",
                {
                    "schema": REVIEW_SCHEMA if confirmation else SCHEMA,
                    "status": "GROUNDING_WITH_FINDINGS",
                    "identity": identity,
                    "object_id": request.object_id,
                    "input_policy": INPUT_POLICY,
                    "policy": asdict(self.policy),
                    "annotation_input_sha256": annotation_identity,
                    **(
                        {"review_confirmation_sha256": confirmation_identity}
                        if confirmation
                        else {}
                    ),
                    "source_fingerprint": hashlib.sha256(encoded(fingerprint).encode()).hexdigest(),
                    "artifact_sha256": {
                        p.relative_to(tx.stage).as_posix(): sha256(p)
                        for p in sorted(tx.stage.rglob("*"))
                        if p.is_file()
                    },
                },
            )
            result = verify_grounding(tx.stage, request)
            tx.publish()
        return {
            "output": str(request.output),
            "geometry_state": report["geometry_state"],
            "scale_applied": False,
            "verification": result,
        }
