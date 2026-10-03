"""Verify derived identities, admitted inputs and exact source K/pose/sensor retention."""

import csv
import json
from pathlib import Path

from cozmo_ingestion import CaptureReader
from cozmo_ingestion.errors import require
from cozmo_ingestion.storage import BundleIntegrity, sha256

from .analysis import SensorIndex
from .media import read_image
from .pipeline import INPUT_POLICY, SCHEMA


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def verify_preprocessing(output: Path, bundle: Path, source_root: Path | None = None) -> dict:
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    require(
        manifest["schema"] == SCHEMA and manifest["status"] == "PREPARED_WITH_FINDINGS",
        "PREPROCESS_NOT_READY",
        str(output),
    )
    require(
        manifest["input_policy"] == INPUT_POLICY,
        "PREPROCESS_INPUT_POLICY_CHANGED",
        "Excluded input boundary",
    )
    require(
        sha256(bundle / "manifest.json") == manifest["source_manifest_sha256"],
        "PREPROCESS_SOURCE_CHANGED",
        "Ingestion identity",
    )
    integrity = BundleIntegrity(output, manifest["artifact_sha256"])
    count = integrity.verify_all()
    reader = CaptureReader(bundle, "ios_preprocessing", source_root)
    reader.verify_bundle()
    require(
        sha256(reader.source_path("wide.mp4")) == manifest["source_video_sha256"],
        "SOURCE_CHANGED",
        "wide.mp4",
    )
    frames, calibration, poses = (
        reader.records("frames"),
        reader.records("calibration"),
        reader.records("poses"),
    )
    ks, ts = {k["id"]: k for k in calibration}, {p["id"]: p for p in poses}
    views = lines(integrity.path("views.jsonl"))
    selected_k, selected_t = (
        lines(integrity.path("calibration.jsonl")),
        lines(integrity.path("poses.jsonl")),
    )
    require(
        bool(views) and len(views) == len(selected_k) == len(selected_t),
        "PREPROCESS_ASSOCIATION_FAILED",
        "Selected views",
    )
    ranks = [v["rank"] for v in views]
    require(
        ranks == sorted(set(ranks)) and all(0 <= r < len(frames) for r in ranks),
        "PREPROCESS_ASSOCIATION_FAILED",
        "Selected ranks",
    )
    for view, k, pose in zip(views, selected_k, selected_t, strict=True):
        f = frames[view["rank"]]
        require(
            all(
                view[key] == f[key]
                for key in (
                    "frame_id",
                    "media_pts_ticks",
                    "media_timebase",
                    "sensor_seconds",
                    "relative_seconds",
                    "calibration_id",
                    "pose_id",
                    "tracking_state",
                )
            )
            and view["source_frame_index"] == int(f["source_frame_index"]),
            "PREPROCESS_ASSOCIATION_FAILED",
            str(view["rank"]),
        )
        require(
            k == ks[f["frame_id"]] and pose == ts[f["frame_id"]],
            "PREPROCESS_GEOMETRY_CHANGED",
            f["frame_id"],
        )
        require(
            view["image"] == f"images/{view['rank']:06d}.jpg"
            and view["thumbnail"] == f"thumbnails/{view['rank']:06d}.jpg",
            "PREPROCESS_IMAGE_ASSOCIATION_FAILED",
            f["frame_id"],
        )
        image = read_image(integrity.path(view["image"]))
        require(
            [image.shape[1], image.shape[0]] == view["image_size"] == k["image_size"]
            and view["pixel_transform"] == [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "PREPROCESS_PIXEL_GRID_CHANGED",
            f["frame_id"],
        )
        integrity.path(view["thumbnail"])
    native_sensors = {}
    for name in ("accelerometer", "gyroscope"):
        with integrity.path(f"imu/{name}.csv").open(newline="", encoding="utf-8") as stream:
            native_sensors[name] = reader.records(name)
            require(
                list(csv.DictReader(stream)) == native_sensors[name],
                "PREPROCESS_SENSOR_CHANGED",
                name,
            )
        reader.source_path(f"{name}.csv")
    reader.source_path("arkit_pose.csv")
    intervals = lines(integrity.path("imu_intervals.jsonl"))
    require(len(intervals) == len(views), "PREPROCESS_IMU_INTERVAL_CHANGED", "Interval count")
    indices = {
        "accelerometer": SensorIndex(
            native_sensors["accelerometer"], ["ax_m_s2", "ay_m_s2", "az_m_s2"]
        ),
        "gyroscope": SensorIndex(native_sensors["gyroscope"], ["gx_rad_s", "gy_rad_s", "gz_rad_s"]),
    }
    previous = float(frames[0]["relative_seconds"])
    for view, interval in zip(views, intervals, strict=True):
        end = float(view["relative_seconds"])
        require(
            interval
            == {
                "frame_id": view["frame_id"],
                **{name: index.interval(previous, end) for name, index in indices.items()},
            },
            "PREPROCESS_IMU_INTERVAL_CHANGED",
            view["frame_id"],
        )
        previous = end
    pairs = lines(integrity.path("pairs.jsonl"))
    require(
        [(p["first_rank"], p["second_rank"]) for p in pairs]
        == list(zip(ranks, ranks[1:], strict=False)),
        "PREPROCESS_PAIR_ASSOCIATION_FAILED",
        "Neighbor identities",
    )
    report = json.loads(integrity.path("report.json").read_text(encoding="utf-8"))
    require(
        report["selected_count"] == len(views)
        and report["source_frame_count"] == len(frames)
        and report["input_policy"] == INPUT_POLICY,
        "PREPROCESS_REPORT_CHANGED",
        "Report identities",
    )
    usage = json.loads(integrity.path("usage.json").read_text(encoding="utf-8"))
    allowed = {
        "frames.csv",
        "calibration.jsonl",
        "trajectory/source_poses.jsonl",
        "imu/accelerometer.csv",
        "imu/gyroscope.csv",
    }
    require(
        usage["profile"] == "ios_preprocessing"
        and all(
            entry.get("asset_id")
            in {"wide.mp4", "arkit_pose.csv", "accelerometer.csv", "gyroscope.csv"}
            if "asset_id" in entry
            else entry.get("artifact") in allowed
            for entry in usage["consumed"]
        ),
        "PREPROCESS_INPUT_LEAK",
        "Usage log",
    )
    return {
        "status": "PASSED",
        "artifacts_verified": count,
        "views_verified": len(views),
        "source_geometry_preserved": True,
        "scale_applied": False,
        "depth_used": False,
        "grounding_used": False,
    }
