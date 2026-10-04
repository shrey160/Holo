"""Recompute diagnostics from source cameras/corners; do not trust a rehashed report."""

import json

from cozmo_ingestion.errors import require
from cozmo_ingestion.storage import BundleIntegrity, sha256
from cozmo_reconstruction.audit_numbers import equivalent

from .analysis import analyze
from .annotations import audit_source, inputs, load_annotations, template
from .confirmation import load_confirmation
from .models import GroundingPolicy
from .pipeline import INPUT_POLICY, REVIEW_SCHEMA, SCHEMA


def verify_grounding(output, request):
    reader = audit_source(request)
    identity, reference, views = inputs(request, reader)
    manifest = json.loads((output / "manifest.json").read_text())
    require(
        manifest["schema"] in (SCHEMA, REVIEW_SCHEMA)
        and manifest["status"] == "GROUNDING_WITH_FINDINGS"
        and manifest["identity"] == identity
        and manifest["object_id"] == request.object_id
        and manifest["input_policy"] == INPUT_POLICY,
        "GROUNDING_SOURCE_CHANGED",
        "Source chain / immutable diagnostic boundary",
    )
    if request.annotations:
        require(
            sha256(request.annotations) == manifest["annotation_input_sha256"],
            "GROUNDING_ANNOTATION_SOURCE_CHANGED",
            "External annotation identity",
        )
    integrity = BundleIntegrity(output, manifest["artifact_sha256"])
    count = integrity.verify_all()
    require(
        json.loads(integrity.path("views.json").read_text()) == views
        and json.loads(integrity.path("reference.json").read_text()) == reference
        and json.loads(integrity.path("policy.json").read_text()) == manifest["policy"],
        "GROUNDING_INPUT_CHANGED",
        "Recomputed camera/reference association",
    )
    annotations = load_annotations(
        integrity.path("annotations.json"), identity, request.object_id, views
    )
    if manifest["annotation_input_sha256"] is not None:
        original = integrity.path("annotation_source.json")
        require(
            sha256(original) == manifest["annotation_input_sha256"]
            and json.loads(original.read_text(encoding="utf-8")) == annotations,
            "GROUNDING_ANNOTATION_SOURCE_CHANGED",
            "Archived original annotation",
        )
    else:
        empty = template(identity, request.object_id)
        empty["annotator"] = "UNANNOTATED"
        require(
            annotations == empty, "GROUNDING_ANNOTATION_SOURCE_CHANGED", "No annotations supplied"
        )
    policy = GroundingPolicy(**manifest["policy"])
    confirmation = None
    if manifest["schema"] == REVIEW_SCHEMA:
        review = integrity.path("review_confirmation.json")
        require(
            sha256(review) == manifest["review_confirmation_sha256"],
            "GROUNDING_REVIEW_SOURCE_CHANGED",
            "Archived review identity",
        )
        confirmation = load_confirmation(
            review, manifest["annotation_input_sha256"], identity, annotations
        )
        if request.review_confirmation:
            require(
                sha256(request.review_confirmation) == manifest["review_confirmation_sha256"],
                "GROUNDING_REVIEW_SOURCE_CHANGED",
                "External review identity",
            )
    else:
        require(
            request.review_confirmation is None,
            "GROUNDING_REVIEW_SOURCE_CHANGED",
            "Historical report has no incorporated review",
        )
    report = analyze(views, reference, annotations, policy, request, confirmation)
    require(
        equivalent(json.loads(integrity.path("report.json").read_text()), report),
        "GROUNDING_REPORT_CHANGED",
        "Recomputed diagnostics, including no-scale-correction state",
    )
    for view in views:
        require(
            sha256(integrity.path(f"images/{view['rank']:06d}.jpg")) == view["image_sha256"],
            "GROUNDING_IMAGE_CHANGED",
            "Native image retained",
        )
    integrity.verify_all()
    return {
        "status": "VERIFIED",
        "artifacts": count,
        "geometry_state": report["geometry_state"],
        "scale_applied": False,
        "physical_accuracy": "UNVERIFIED",
    }
