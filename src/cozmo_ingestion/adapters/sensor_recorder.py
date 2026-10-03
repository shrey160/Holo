"""Strict Sensor Recorder Pro 1.5/build 5 ARKit export adapter."""

import csv
import json
from pathlib import Path

from ..clocks import associate
from ..contracts import DEFAULT_POLICY, IngestionPolicy
from ..errors import require
from ..models import SourceCapture, VideoInspection
from ..numeric import number
from .sensor_recorder_schema import ADAPTER, POSE_HEADER, ROLES, STREAM_HEADERS


def load_csv(path: Path, expected: list[str]) -> tuple[list[dict], list[dict]]:
    """Validate a commented source CSV while preserving strings and source line numbers."""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    comments = [
        {"line": i + 1, "text": line}
        for i, line in enumerate(lines)
        if line.lstrip().startswith("#")
    ]
    content = [
        (i + 1, line)
        for i, line in enumerate(lines)
        if line.strip() and not line.lstrip().startswith("#")
    ]
    require(bool(content), "EMPTY_STREAM", path.name)
    reader = csv.DictReader(line for _, line in content)
    require(reader.fieldnames == expected, "UNSUPPORTED_HEADER", path.name)
    rows = list(reader)
    require(bool(rows), "EMPTY_STREAM", path.name)
    for i, row in enumerate(rows):
        require(None not in row and None not in row.values(), "MALFORMED_ROW", f"{path.name}: {i}")
        for key, value in row.items():
            if key != "tracking_state":
                number(value)
        row["_source_line"] = content[i + 1][0]
    times = [number(r["sensor_sec"]) for r in rows]
    require(
        all(b > a for a, b in zip(times, times[1:], strict=False)), "NONMONOTONIC_TIME", path.name
    )
    return rows, comments


def validate_metadata(meta: dict) -> dict:
    """Admit only the inspected version, stream schemas and declared conventions."""
    require(
        meta.get("format_version") == 1
        and meta.get("app", {}).get("name") == "com.grape.SensorRecorder"
        and meta["app"].get("version") == "1.5"
        and str(meta["app"].get("build")) == "5",
        "UNSUPPORTED_EXPORT_VERSION",
        "Adapter supports Sensor Recorder format 1, version 1.5/build 5",
    )
    require(
        meta.get("capture_mode") == "arkit" and meta.get("state") == "finished",
        "UNFINISHED_OR_WRONG_MODE",
        "Require a finished ARKit capture",
    )
    conventions = meta.get("coordinate_conventions", {})
    require(
        conventions.get("pose") == "T_world_camera (parent_from_child): p_world = R * p_camera + t"
        and conventions.get("recorded_camera") == "OpenCV/Rerun RDF: x right, y down, z forward"
        and conventions.get("quaternion_order") == "qw,qx,qy,qz"
        and conventions.get("pixel_coordinates") == "origin top-left; x right, y down",
        "UNSUPPORTED_COORDINATES",
        "No automatic guessing of pose axes/direction/order",
    )
    streams = meta.get("streams", {})
    for key in ["wide_camera", "arkit_pose"]:
        stream = streams.get(key, {})
        require(
            stream.get("enabled") is True
            and stream.get("media_file") == "wide.mp4"
            and stream.get("index_file") == "arkit_pose.csv"
            and stream.get("schema") == POSE_HEADER,
            "UNSUPPORTED_CAMERA_SCHEMA",
            key,
        )
    for key in ["ultrawide_camera", "front_camera", "telephoto_camera"]:
        require(not streams.get(key, {}).get("enabled", False), "UNSUPPORTED_MULTICAMERA", key)
    require(
        streams["arkit_pose"].get("world_alignment") == "gravity",
        "UNSUPPORTED_WORLD",
        "Require declared gravity-aligned world",
    )
    return streams


class SensorRecorderAdapter:
    """Parse this supported export and establish its camera/media association."""

    name = ADAPTER
    stream_headers = STREAM_HEADERS

    def load(self, source: Path, asset_hashes: dict[str, str]) -> SourceCapture:
        require("meta.json" in asset_hashes, "MISSING_METADATA", "meta.json")
        meta = json.loads((source / "meta.json").read_text(encoding="utf-8"))
        streams = validate_metadata(meta)
        for name in ["wide.mp4", "arkit_pose.csv", "accelerometer.csv", "gyroscope.csv"]:
            require(name in asset_hashes, "MISSING_REQUIRED_STREAM", name)
        rows, comments = load_csv(source / "arkit_pose.csv", POSE_HEADER)
        tables, stream_notes = {}, {}
        for key, header in STREAM_HEADERS.items():
            declaration = streams.get(key, {})
            required = key in ["accelerometer", "gyroscope"]
            require(
                not required or declaration.get("enabled") is True, "MISSING_REQUIRED_STREAM", key
            )
            if declaration.get("enabled"):
                require(
                    declaration.get("file") == key + ".csv" and declaration.get("schema") == header,
                    "UNSUPPORTED_STREAM_SCHEMA",
                    key,
                )
                require(key + ".csv" in asset_hashes, "MISSING_ENABLED_STREAM", key)
                if key in ["accelerometer", "device_motion", "imu"]:
                    require(
                        declaration.get("acceleration_conversion")
                        == "CoreMotion g converted to m/s^2 using 9.80665",
                        "UNSUPPORTED_UNITS",
                        key,
                    )
                tables[key], stream_notes[key] = load_csv(source / (key + ".csv"), header)

        return SourceCapture(source, meta, streams, rows, comments, tables, stream_notes)

    def associate(
        self,
        capture: SourceCapture,
        video: VideoInspection,
        policy: IngestionPolicy = DEFAULT_POLICY,
    ) -> tuple[dict, list[int]]:
        return associate(capture.camera_rows, video, policy)

    def inventory(self, source: Path) -> list[dict]:
        from ..storage import sha256

        items = []
        for path in sorted(source.rglob("*")):
            if path.is_file():
                require(
                    not path.is_symlink() and path.resolve().is_relative_to(source),
                    "SOURCE_PATH_ESCAPE",
                    str(path),
                )
                relative = path.relative_to(source).as_posix()
                role = ROLES.get(relative, "auxiliary_excluded")
                if relative.startswith(("depth/", "confidence/", "lidar_depth/")):
                    role = "measured_depth_excluded"
                items.append(
                    {
                        "id": relative,
                        "root": "capture",
                        "path": relative,
                        "role": role,
                        "bytes": path.stat().st_size,
                        "sha256": sha256(path),
                    }
                )
        return items
