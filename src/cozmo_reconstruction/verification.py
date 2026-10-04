"""Independent source/camera/feature/track audit before publishing derived geometry."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import numpy as np

from cozmo_ingestion.errors import require
from cozmo_ingestion.storage import BundleIntegrity
from cozmo_preprocessing.verification import lines

from .analysis import analyze, point_metrics
from .audit_numbers import equivalent
from .cameras import convert_camera, select_pairs
from .inputs import PreparedInput
from .models import ReconstructionPolicy, ReconstructionRequest
from .pipeline import INPUT_POLICY, SCHEMA


def verify_reconstruction(output: Path, prepared: Path, bundle: Path, source_root=None) -> dict:
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    require(
        manifest["schema"] == SCHEMA
        and manifest["status"] == "SPARSE_RECONSTRUCTED_WITH_FINDINGS"
        and manifest["input_policy"] == INPUT_POLICY,
        "RECONSTRUCTION_NOT_READY",
        "Manifest/policy",
    )
    integrity = BundleIntegrity(output, manifest["artifact_sha256"])
    count = integrity.verify_all()
    mapping = json.loads(integrity.path("input_mapping.json").read_text(encoding="utf-8"))
    policy = ReconstructionPolicy(**manifest["policy"])
    require(
        json.loads(integrity.path("policy.json").read_text(encoding="utf-8")) == manifest["policy"],
        "RECONSTRUCTION_POLICY_CHANGED",
        "Backend policy",
    )
    data = PreparedInput(
        ReconstructionRequest(
            prepared, bundle, output, source_root, tuple(v["rank"] for v in mapping)
        ),
        policy,
    )
    require(
        data.snapshot == manifest["source_identity"] and data.mapping == mapping,
        "RECONSTRUCTION_SOURCE_CHANGED",
        "Image/calibration/pose identities",
    )
    for view in mapping:
        require(
            manifest["artifact_sha256"][f"images/{view['image']}"] == view["image_sha256"],
            "RECONSTRUCTION_IMAGE_CHANGED",
            view["image"],
        )
    expected_pairs = "".join(f"{a} {b}\n" for a, b in select_pairs(mapping, policy))
    require(
        integrity.path("pairs.txt").read_text(encoding="utf-8") == expected_pairs,
        "RECONSTRUCTION_PAIRS_CHANGED",
        "Candidate schedule",
    )
    cameras = json.loads(integrity.path("cameras.json").read_text(encoding="utf-8"))
    before = json.loads(integrity.path("cameras_before.json").read_text(encoding="utf-8"))
    from .colmap import assert_fixed, camera_records, export_points, pc

    require(pc.__version__ == "4.2.1", "RECONSTRUCTION_BACKEND_VERSION", pc.__version__)
    assert_fixed(before, cameras)
    require(
        len(cameras) == len(mapping) and len({c["rank"] for c in cameras}) == len(mapping),
        "RECONSTRUCTION_CAMERA_INVALID",
        "Camera count/identity",
    )
    source_by_rank = {v["rank"]: v for v in mapping}
    for camera in cameras:
        view = source_by_rank[camera["rank"]]
        expected = convert_camera(view["calibration"], view["pose"], policy.principal_point_shift)
        require(
            camera["image"] == view["image"]
            and camera["model"] == "PINHOLE"
            and camera["image_size"] == expected["image_size"]
            and all(
                np.allclose(camera[k], expected[k], atol=1e-10, rtol=0)
                for k in ("params", "camera_from_world", "center_m")
            ),
            "RECONSTRUCTION_CAMERAS_CHANGED",
            str(view["rank"]),
        )
        camera["K"] = expected["K"]
    points = lines(integrity.path("points.jsonl"))
    candidates = lines(integrity.path("candidate_points.jsonl"))
    require(
        len({p["point_id"] for p in candidates}) == len(candidates),
        "RECONSTRUCTION_TRACK_INVALID",
        "Duplicate point IDs",
    )
    by_rank = {c["rank"]: c for c in cameras}
    expected_points = [p for p in candidates if point_metrics(p, by_rank, policy)["accepted"]]
    require(
        points == expected_points, "RECONSTRUCTION_TRACK_INVALID", "Accepted/rejected partition"
    )
    model = pc.Reconstruction(integrity.path("model/cameras.bin").parent)
    by_name = {v["image"]: v for v in mapping}
    assert_fixed(before, camera_records(model, by_name))
    require(
        export_points(model, by_name) == points, "RECONSTRUCTION_TRACK_INVALID", "Model lineage"
    )
    # PyCOLMAP Database.open initializes/writes schema metadata even on read access.
    # Published evidence must remain byte-identical: inspect its known schema read-only.
    with closing(
        sqlite3.connect(integrity.path("database.db").resolve().as_uri() + "?mode=ro", uri=True)
    ) as db:
        seen = set()
        db_images = {
            row[0]: row[1:] for row in db.execute("SELECT image_id, name, camera_id FROM images")
        }
        keypoints = {
            image_id: np.frombuffer(blob, dtype=np.float32).reshape(rows, cols)
            for image_id, rows, cols, blob in db.execute(
                "SELECT image_id, rows, cols, data FROM keypoints"
            )
        }
        for point in points:
            for obs in point["observations"]:
                key = (obs["image_id"], obs["keypoint_index"])
                require(key not in seen, "RECONSTRUCTION_TRACK_INVALID", "Feature assigned twice")
                seen.add(key)
                camera = by_rank[obs["rank"]]
                image = db_images[obs["image_id"]]
                xy = keypoints[obs["image_id"]][obs["keypoint_index"], :2]
                require(
                    image[0] == camera["image"]
                    and image[1] == camera["camera_id"]
                    and np.allclose(xy, obs["xy"], atol=1e-6, rtol=0),
                    "RECONSTRUCTION_TRACK_INVALID",
                    "Database feature lineage",
                )
    report = json.loads(integrity.path("report.json").read_text(encoding="utf-8"))
    recomputed = analyze(mapping, points, candidates, cameras, policy)
    require(
        all(equivalent(report[k], value) for k, value in recomputed.items()),
        "RECONSTRUCTION_REPORT_CHANGED",
        "Recomputed geometry",
    )
    require(
        report["excluded_prepared_ranks"] == sorted(set(data.all_ranks) - set(source_by_rank))
        and report["pair_candidates"] == len(select_pairs(mapping, policy)),
        "RECONSTRUCTION_REPORT_CHANGED",
        "Selection and pairing counts",
    )
    integrity.verify_all()
    return {
        "status": "PASSED",
        "verified_artifacts": count,
        "views": len(mapping),
        "accepted_points": len(points),
        "source_geometry_retained": True,
        "backend_model_and_feature_lineage": "PASSED",
        "grounding_applied": False,
        "lidar_used": False,
        "accuracy": "UNVERIFIED",
    }
