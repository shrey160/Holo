"""Replay native Stray CSV values against associated canonical records."""

import json
from pathlib import Path

from .adapters.stray import IMU_HEADER, ODOMETRY_HEADER, StrayAdapter, camera_rows, native_rows
from .contracts import IngestionPolicy
from .errors import require
from .numeric import number, quaternion_pose
from .reader import CaptureReader
from .storage import sha256


def verify_observations(
    reader: CaptureReader,
    source: Path,
    policy: IngestionPolicy,
    count: int,
    replay: str | Path | None,
) -> dict:
    native = native_rows(source / "odometry.csv", ODOMETRY_HEADER)
    rows = camera_rows(native)[1:]
    frames, poses, calibration = (
        reader.records("frames"),
        reader.records("poses"),
        reader.records("calibration"),
    )
    require(
        len(frames)
        == len(poses)
        == len(calibration)
        == len(rows)
        == reader.manifest["frame_count"],
        "EXPORT_COUNT_MISMATCH",
        "Stray decoded association counts",
    )
    require(
        reader.manifest.get("source_camera_record_count") == len(native)
        and reader.manifest.get("unassociated_source_frame_indices") == [0],
        "EXPORT_ASSOCIATION_MISMATCH",
        "Initial odometry record must remain unassociated",
    )
    width, height = calibration[0]["image_size"]
    replay_source = StrayAdapter().load(
        source, {a["path"]: a["sha256"] for a in reader.assets.values() if a["root"] == "capture"}
    )
    retained = json.loads(
        reader.integrity.path("trajectory/unassociated_source_poses.jsonl").read_text(
            encoding="utf-8"
        )
    )
    require(
        retained == replay_source.camera_rows[0], "SOURCE_VALUE_CHANGED", "Unassociated first pose"
    )
    origin = number(rows[0]["sensor_sec"])
    require(
        len({frame["frame_id"] for frame in frames}) == len(frames), "DUPLICATE_FRAME", "Frame IDs"
    )
    for rank, (raw, frame, pose, k) in enumerate(
        zip(rows, frames, poses, calibration, strict=True)
    ):
        require(
            int(frame["decoded_rank"]) == rank
            and int(frame["source_frame_index"]) == rank + 1
            and frame["video_asset_id"] == "rgb.mp4"
            and frame["frame_id"] == pose["id"] == k["id"]
            and pose["source_frame_index"] == k["source_frame_index"] == rank + 1,
            "EXPORT_ASSOCIATION_MISMATCH",
            str(rank),
        )
        require(
            frame["sensor_seconds"] == raw["sensor_sec"]
            and frame["record_slot"] == raw["record_slot"]
            and int(frame["source_line"]) == raw["_source_line"]
            and not frame["utc_seconds"]
            and not frame["exposure_seconds"]
            and frame["tracking_state"] == "unreported"
            and number(frame["relative_seconds"]) == number(raw["sensor_sec"]) - origin,
            "SOURCE_VALUE_CHANGED",
            str(rank),
        )
        expected, _ = quaternion_pose(raw, policy)
        require(
            pose["world_from_camera"] == expected
            and pose["source_quaternion_wxyz"] == [raw[key] for key in ("qw", "qx", "qy", "qz")]
            and pose["source_translation_m"] == [raw[key] for key in ("tx_m", "ty_m", "tz_m")],
            "EXPORTED_POSE_CHANGED",
            str(rank),
        )
        require(
            k["K"]
            == [
                [float(raw["fx_px"]), 0, float(raw["cx_px"])],
                [0, float(raw["fy_px"]), float(raw["cy_px"])],
                [0, 0, 1],
            ]
            and k["image_size"] == [width, height],
            "EXPORTED_K_CHANGED",
            str(rank),
        )
    original = native_rows(source / "imu.csv", IMU_HEADER)
    exported = reader.records("native_imu")
    require(len(original) == len(exported), "EXPORTED_SENSOR_COUNT_CHANGED", "imu")
    for raw, row in zip(original, exported, strict=True):
        require(
            all(raw[key] == row[key] for key in IMU_HEADER)
            and row["sensor_sec"] == raw["timestamp"]
            and int(row["source_line"]) == raw["_source_line"]
            and number(row["relative_seconds"]) == number(raw["timestamp"]) - origin,
            "EXPORTED_SENSOR_VALUE_CHANGED",
            "imu",
        )
    for asset in reader.assets.values():
        if asset["root"] == "capture":
            require(
                sha256(source / asset["path"]) == asset["sha256"], "SOURCE_CHANGED", asset["id"]
            )
    require(
        reader.records("annotations")["scale_applied"] is False,
        "UNEXPECTED_SCALE_CHANGE",
        "Ingestion cannot correct scale",
    )
    equal = None
    if replay:
        other = CaptureReader(replay, source_root=source)
        other.verify_bundle()
        require(
            other.manifest == reader.manifest,
            "NONDETERMINISTIC_REPLAY",
            "Manifest identities differ",
        )
        equal = True
    return {
        "status": "PASSED",
        "frames_verified": len(frames),
        "artifacts_verified": count,
        "sensor_rows_verified": {"imu": len(original)},
        "source_values_preserved": True,
        "unassociated_source_frame_indices": [0],
        "scale_applied": False,
        "deterministic_replay_equal": equal,
    }
