"""Recompute sample classifications, floor frame and spans; reject rehashed false results."""

import json

import numpy as np

from cozmo_ingestion.errors import require
from cozmo_ingestion.storage import BundleIntegrity, sha256
from cozmo_reconstruction.audit_numbers import equivalent

from .analysis import analyze
from .models import BoundaryPolicy
from .pipeline import INPUT_POLICY, SCHEMA
from .reviews import inputs, load_review, source_audit, template


def verify_boundaries(output, request):
    source_audit(request)
    identity, plane_report, views = inputs(request)
    manifest = json.loads((output / "manifest.json").read_text())
    require(
        manifest["schema"] == SCHEMA
        and manifest["status"] == "PARTIAL_BOUNDARIES_WITH_FINDINGS"
        and manifest["identity"] == identity
        and manifest["input_policy"] == INPUT_POLICY,
        "BOUNDARY_SOURCE_CHANGED",
        "Source chain and no-correction policy",
    )
    integrity = BundleIntegrity(output, manifest["artifact_sha256"])
    count = integrity.verify_all()
    require(
        json.loads(integrity.path("views.json").read_text()) == views
        and json.loads(integrity.path("policy.json").read_text()) == manifest["policy"],
        "BOUNDARY_INPUT_CHANGED",
        "Source views and policy",
    )
    review = load_review(integrity.path("review.json"), identity, plane_report["planes"], views)
    if manifest["review_input_sha256"] is None:
        require(
            review == template(identity), "BOUNDARY_REVIEW_SOURCE_CHANGED", "No review supplied"
        )
    else:
        archived = integrity.path("review_input.json")
        require(
            sha256(archived) == manifest["review_input_sha256"]
            and json.loads(archived.read_text(encoding="utf-8")) == review,
            "BOUNDARY_REVIEW_SOURCE_CHANGED",
            "Exact archived original review",
        )
    if request.review:
        require(
            sha256(request.review) == manifest["review_input_sha256"],
            "BOUNDARY_REVIEW_SOURCE_CHANGED",
            "External review identity",
        )
    policy = BoundaryPolicy(**manifest["policy"])
    report, arrays = analyze(request, review, plane_report, policy)
    require(
        equivalent(json.loads(integrity.path("report.json").read_text()), report),
        "BOUNDARY_REPORT_CHANGED",
        "Recomputed floor/partial spans/missing states",
    )
    with np.load(integrity.path("reviewed_observations.npz")) as saved:
        require(set(saved.files) == set(arrays), "BOUNDARY_OBSERVATIONS_CHANGED", "Array fields")
        for key, expected in arrays.items():
            actual = saved[key]
            require(
                actual.shape == expected.shape
                and actual.dtype == expected.dtype
                and (
                    np.allclose(actual, expected, atol=1e-10, rtol=1e-12)
                    if key == "xyz_m"
                    else np.array_equal(actual, expected)
                ),
                "BOUNDARY_OBSERVATIONS_CHANGED",
                key,
            )
    for view in views:
        if not any(r["rank"] == view["rank"] for r in review["regions"]):
            continue
        require(
            sha256(integrity.path(f"images/{view['rank']:06d}.jpg")) == view["source_rgb_sha256"]
            and sha256(integrity.path(f"source_overlays/{view['rank']:06d}.jpg"))
            == view["evidence_overlay_sha256"],
            "BOUNDARY_IMAGE_CHANGED",
            "Exact source images/overlays",
        )
    integrity.verify_all()
    return {
        "status": "VERIFIED",
        "artifacts": count,
        "supported_segments": report["supported_segments"],
        "physical_accuracy": "UNVERIFIED",
        "closed_room_polygon": None,
        "scale_applied": False,
    }
