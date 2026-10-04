"""Versioned Stray-style raw-depth source parsing.

Exporter identity/version are unverified. Depth units, pose direction and world
frame follow the inspected reference encoder and are recorded as assumptions,
never silently converted. No RGB-to-depth axis flip is added.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from ...adapters.stray import IMU_HEADER, ODOMETRY_HEADER, native_rows
from ...errors import require
from ...numeric import integer, number

ADAPTER = "stray-raw-depth-v1"
SOURCE_FORMAT = "stray-raw-depth"
REQUIRED_FILES = ("rgb.mp4", "odometry.csv", "imu.csv", "camera_matrix.csv")

CONVENTION_EVIDENCE = (
    "FORMAT_REFERENCE_ASSUMED; exporter identity/version and calibration/physical "
    "registration unverified"
)


@dataclass(frozen=True)
class StrayLidarSource:
    root: Path
    rgb: Path
    odometry: list[dict]
    imu: list[dict]
    matrix: list[list[float]]
    depth: dict[int, Path]
    confidence: dict[int, Path]

    @property
    def native_ids(self) -> list[int]:
        return [integer(row["frame"]) for row in self.odometry]


def _frames(directory: Path, required: bool) -> dict[int, Path]:
    if not directory.is_dir():
        require(not required, "MISSING_REQUIRED_STREAM", str(directory))
        return {}
    files = sorted(directory.glob("*.png"))
    require(not required or bool(files), "MISSING_REQUIRED_STREAM", str(directory))
    mapping: dict[int, Path] = {}
    for path in files:
        require(path.stem.isdigit(), "INVALID_FRAME_FILENAME", path.name)
        mapping[int(path.stem)] = path
    return mapping


def load(source: Path, require_depth: bool = True) -> StrayLidarSource:
    require(source.is_dir(), "SOURCE_NOT_FOUND", str(source))
    for name in REQUIRED_FILES:
        require((source / name).is_file(), "MISSING_REQUIRED_STREAM", name)
    odometry = native_rows(source / "odometry.csv", ODOMETRY_HEADER)
    require(
        [integer(row["frame"]) for row in odometry] == list(range(len(odometry))),
        "FRAME_ID_MISMATCH",
        "Require sequential odometry frame IDs",
    )
    with (source / "camera_matrix.csv").open(encoding="utf-8", newline="") as stream:
        matrix = list(csv.reader(stream, skipinitialspace=True))
    require(
        len(matrix) == 3 and all(len(row) == 3 for row in matrix),
        "INVALID_INTRINSICS",
        "camera_matrix.csv must be 3 by 3",
    )
    matrix = [[float(number(value)) for value in row] for row in matrix]
    final = odometry[-1]
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
    depth = _frames(source / "depth", required=require_depth)
    ids = {integer(row["frame"]) for row in odometry}
    if depth:
        require(
            set(depth) == ids,
            "DEPTH_ID_MISMATCH",
            "Depth frames must match odometry frame IDs exactly",
        )
    confidence = _frames(source / "confidence", required=False)
    if confidence:
        require(
            set(confidence) == set(depth),
            "CONFIDENCE_ID_MISMATCH",
            "Confidence frames must match depth frame IDs exactly",
        )
    imu = native_rows(source / "imu.csv", IMU_HEADER)
    return StrayLidarSource(source, source / "rgb.mp4", odometry, imu, matrix, depth, confidence)
