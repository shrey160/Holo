"""Supplied Stray-style exports: native values and explicit initial RGB discard.

Exporter identity/version are unknown. Axes follow the inspected reference encoder;
acceleration units remain unresolved rather than silently converting raw readings.
"""

import csv
from fractions import Fraction
from pathlib import Path

from ..contracts import DEFAULT_POLICY, IngestionPolicy
from ..errors import require
from ..models import SourceCapture, VideoInspection
from ..numeric import integer, number
from .sensor_recorder import SensorRecorderAdapter

ADAPTER = "stray-layout-supplied-v1"
ODOMETRY_HEADER = [
    "timestamp",
    "frame",
    "x",
    "y",
    "z",
    "qx",
    "qy",
    "qz",
    "qw",
    "fx",
    "fy",
    "cx",
    "cy",
    "distortion_center_x",
    "distortion_center_y",
]
IMU_HEADER = ["timestamp", "a_x", "a_y", "a_z", "alpha_x", "alpha_y", "alpha_z"]


def native_rows(path: Path, header: list[str]) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, skipinitialspace=True)
        require(next(reader, None) == header, "UNSUPPORTED_HEADER", path.name)
        result = []
        for values in reader:
            require(len(values) == len(header), "MALFORMED_ROW", path.name)
            row = dict(zip(header, (value.strip() for value in values), strict=True))
            for key, value in row.items():
                if key.startswith("distortion_center") and not value:
                    continue
                number(value)
            row["_source_line"] = reader.line_num
            result.append(row)
    require(bool(result), "EMPTY_STREAM", path.name)
    times = [number(row["timestamp"]) for row in result]
    require(
        all(b > a for a, b in zip(times, times[1:], strict=False)), "NONMONOTONIC_TIME", path.name
    )
    return result


def camera_rows(rows: list[dict], width: int = 0, height: int = 0) -> list[dict]:
    """Rename fields without changing numeric strings or inventing absent metadata."""
    return [
        {
            "frame_index": row["frame"],
            "record_slot": row["frame"],
            "sensor_sec": row["timestamp"],
            "utc_sec": "",
            **{f"t{axis}_m": row[axis] for axis in "xyz"},
            **{key: row[key] for key in ("qw", "qx", "qy", "qz")},
            **{key + "_px": row[key] for key in ("fx", "fy", "cx", "cy")},
            "exposure_sec": "",
            "tracking_state": "unreported",
            "width_px": str(width),
            "height_px": str(height),
            "_source_line": row["_source_line"],
        }
        for row in rows
    ]


class StrayAdapter:
    name = ADAPTER
    required_files = ("rgb.mp4", "odometry.csv", "imu.csv", "camera_matrix.csv")
    stream_headers = {"imu": [*IMU_HEADER, "sensor_sec"]}

    def inventory(self, source: Path) -> list[dict]:
        items = SensorRecorderAdapter().inventory(source)
        for item in items:
            item["role"] = {
                "rgb.mp4": "rgb",
                "odometry.csv": "pose_calibration",
                "camera_matrix.csv": "pose_calibration",
                "imu.csv": "imu_native",
            }.get(item["path"], item["role"])
            if item["path"].startswith("confidence/"):
                item["role"] = "measured_depth_excluded"
        return items

    def load(self, source: Path, asset_hashes: dict[str, str]) -> SourceCapture:
        for name in self.required_files:
            require(name in asset_hashes, "MISSING_REQUIRED_STREAM", name)
        rows = native_rows(source / "odometry.csv", ODOMETRY_HEADER)
        require(
            [integer(row["frame"]) for row in rows] == list(range(len(rows))),
            "FRAME_ID_MISMATCH",
            "Require sequential odometry IDs",
        )
        with (source / "camera_matrix.csv").open(encoding="utf-8", newline="") as stream:
            matrix = list(csv.reader(stream, skipinitialspace=True))
        require(
            len(matrix) == 3 and all(len(row) == 3 for row in matrix),
            "INVALID_INTRINSICS",
            "camera_matrix.csv must be 3 by 3",
        )
        matrix = [[float(number(value)) for value in row] for row in matrix]
        final = rows[-1]
        require(
            matrix
            == [
                [float(final["fx"]), 0, float(final["cx"])],
                [0, float(final["fy"]), float(final["cy"])],
                [0, 0, 1],
            ],
            "CALIBRATION_MISMATCH",
            "Legacy camera matrix must match final per-frame K",
        )
        depth = False
        for directory in ("depth", "confidence"):
            names = [name for name in asset_hashes if name.startswith(directory + "/")]
            if names:
                depth = True
                require(
                    set(names) == {f"{directory}/{row['frame']}.png" for row in rows},
                    "DEPTH_ID_MISMATCH",
                    directory,
                )
        imu = native_rows(source / "imu.csv", IMU_HEADER)
        metadata = {
            "source_format": "stray-layout",
            "app": {"name": "UNKNOWN; Stray-style layout", "version": None},
            "evidence": "FORMAT_REFERENCE_ASSUMED; source exporter identity unverified",
            "metadata_origin": "ADAPTER_DERIVED; export has no metadata file",
            "coordinate_conventions": {"pixel_orientation": "native; no rotation metadata"},
            "native_camera_record_count": len(rows),
            "legacy_camera_matrix": matrix,
            "reference_encoder_revision": "ec3e1dc9d33f8df2289ede6a5c59f7991d1a6bbb",
        }
        return SourceCapture(
            source,
            metadata,
            {"lidar_depth": {"enabled": depth}},
            camera_rows(rows),
            [],
            {"imu": [{**row, "sensor_sec": row["timestamp"]} for row in imu]},
            {},
        )

    def associate(
        self,
        capture: SourceCapture,
        video: VideoInspection,
        policy: IngestionPolicy = DEFAULT_POLICY,
    ) -> tuple[dict, list[int]]:
        """One initial negative-PTS discard, with an independently checked affine clock."""
        rows = capture.camera_rows
        ticks = [integer(row["best_effort_timestamp"]) for row in video.frames]
        discarded = video.discarded_packets
        require(
            len(rows) == len(ticks) + 1 and len(discarded) == 1,
            "FRAME_COUNT_MISMATCH",
            "Require exactly one initial discarded RGB observation",
        )
        require(
            integer(discarded[0]["pts"]) < 0 and integer(discarded[0]["pts"]) < ticks[0],
            "UNSUPPORTED_DISCARD",
            "Discard must precede decoded RGB",
        )
        require(
            all(b > a for a, b in zip(ticks, ticks[1:], strict=False)) and len(ticks) >= 3,
            "NONMONOTONIC_PTS",
            "Require at least three increasing decoded timestamps",
        )
        timebase = Fraction(video.stream["time_base"])
        require(timebase > 0, "INVALID_TIMEBASE", "Positive media timebase")
        x = [float((tick - ticks[0]) * timebase) for tick in ticks]
        y = [float(number(row["sensor_sec"]) - number(rows[1]["sensor_sec"])) for row in rows[1:]]
        mx, my = sum(x) / len(x), sum(y) / len(y)
        slope = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / sum(
            (a - mx) ** 2 for a in x
        )
        intercept = my - slope * mx
        residual = max(abs(b - (intercept + slope * a)) for a, b in zip(x, y, strict=True))
        require(
            abs(slope - 1) <= 0.01 and residual <= 0.010,
            "FRAME_CLOCK_MISMATCH",
            "Affine clock must support the initial-discard mapping",
        )
        capture.metadata["unassociated_camera_records"] = [rows[0]]
        capture.camera_rows = rows[1:]
        for row in capture.camera_rows:
            row["width_px"], row["height_px"] = (
                str(video.stream["width"]),
                str(video.stream["height"]),
            )
        return {
            "method": "decoded rank i -> odometry frame i+1; one initial negative-PTS discard",
            "unassociated_source_frame_indices": [0],
            "media_timebase": str(timebase),
            "affine_slope": slope,
            "affine_relative_intercept_seconds": intercept,
            "maximum_residual_seconds": residual,
            "slope_tolerance": 0.01,
            "residual_tolerance_seconds": 0.010,
            "physical_synchronization": "UNVERIFIED",
        }, ticks
