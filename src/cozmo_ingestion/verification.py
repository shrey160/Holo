"""Verify the stored canonical bundle, source associations and optional replay equality."""

import csv
from pathlib import Path

from .adapters.sensor_recorder import POSE_HEADER, STREAM_HEADERS, load_csv
from .contracts import IngestionPolicy
from .errors import require
from .numeric import number, quaternion_pose
from .reader import CaptureReader
from .storage import sha256


def verify(folder: str | Path, source: str | Path, replay: str | Path | None = None) -> dict:
    """Audit every stored observation against its source; optionally compare replay."""
    reader = CaptureReader(folder, source_root=source)
    policy = IngestionPolicy(**reader.manifest["policy"])
    count = reader.verify_bundle()
    rows, _ = load_csv(Path(source) / "arkit_pose.csv", POSE_HEADER)
    origin = number(rows[0]["sensor_sec"])
    frames = reader.records("frames")
    poses = reader.records("poses")
    calibration = reader.records("calibration")
    require(
        len(frames)
        == len(rows)
        == len(poses)
        == len(calibration)
        == reader.manifest["frame_count"],
        "EXPORT_COUNT_MISMATCH",
        "Canonical frame, pose and K counts",
    )
    require(len({f["frame_id"] for f in frames}) == len(frames), "DUPLICATE_FRAME", "Frame IDs")
    for i, (source_row, frame, pose, k) in enumerate(
        zip(rows, frames, poses, calibration, strict=True)
    ):
        require(
            int(frame["source_frame_index"]) == i
            and int(frame["decoded_rank"]) == i
            and frame["frame_id"] == pose["id"] == k["id"],
            "EXPORT_ASSOCIATION_MISMATCH",
            str(i),
        )
        require(
            frame["sensor_seconds"] == source_row["sensor_sec"]
            and frame["tracking_state"] == source_row["tracking_state"],
            "SOURCE_VALUE_CHANGED",
            str(i),
        )
        require(
            number(frame["relative_seconds"]) == number(source_row["sensor_sec"]) - origin
            and frame["record_slot"] == source_row["record_slot"],
            "EXPORTED_TIME_CHANGED",
            str(i),
        )
        expected, _ = quaternion_pose(source_row, policy)
        require(pose["world_from_camera"] == expected, "EXPORTED_POSE_CHANGED", str(i))
        require(
            [k["K"][0][0], k["K"][1][1], k["K"][0][2], k["K"][1][2]]
            == [float(source_row[n]) for n in ["fx_px", "fy_px", "cx_px", "cy_px"]],
            "EXPORTED_K_CHANGED",
            str(i),
        )
    sensor_rows_verified = {}
    for stream, header in STREAM_HEADERS.items():
        if reader.manifest["capabilities"][stream] != "AVAILABLE":
            continue
        original, _ = load_csv(Path(source) / (stream + ".csv"), header)
        # The combined IMU is retained for provenance, not admitted as a raw-IMU substitute by the reader.
        if stream == "imu":
            path = reader.integrity.path("imu/imu.csv")
            with path.open(newline="", encoding="utf-8") as file:
                exported = list(csv.DictReader(file))
        else:
            exported = reader.records(stream)
        require(len(original) == len(exported), "EXPORTED_SENSOR_COUNT_CHANGED", stream)
        for i, (raw, canonical) in enumerate(zip(original, exported, strict=True)):
            require(
                all(raw[key] == canonical[key] for key in header)
                and int(canonical["source_line"]) == raw["_source_line"]
                and number(canonical["relative_seconds"]) == number(raw["sensor_sec"]) - origin,
                "EXPORTED_SENSOR_VALUE_CHANGED",
                f"{stream}: {i}",
            )
        sensor_rows_verified[stream] = len(original)
    for asset in reader.assets.values():
        if asset["root"] == "capture":
            require(
                sha256(Path(source) / asset["path"]) == asset["sha256"],
                "SOURCE_CHANGED",
                asset["id"],
            )
    annotation = reader.records("annotations")
    require(
        annotation["scale_applied"] is False,
        "UNEXPECTED_SCALE_CHANGE",
        "Ingestion cannot apply scale correction",
    )
    replay_equal = None
    if replay:
        other = CaptureReader(replay, source_root=source)
        other.verify_bundle()
        require(
            reader.manifest == other.manifest,
            "NONDETERMINISTIC_REPLAY",
            "Manifest/content identities differ",
        )
        replay_equal = True
    return {
        "status": "PASSED",
        "frames_verified": len(frames),
        "artifacts_verified": count,
        "sensor_rows_verified": sensor_rows_verified,
        "source_values_preserved": True,
        "scale_applied": False,
        "deterministic_replay_equal": replay_equal,
    }
