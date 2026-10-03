"""Synthetic capture fixtures and media port used by unit tests."""

import copy
import unittest

from cozmo_ingestion import IngestionPipeline, IngestionRequest
from cozmo_ingestion.adapters.sensor_recorder import POSE_HEADER, STREAM_HEADERS
from cozmo_ingestion.models import VideoInspection
from cozmo_ingestion.storage import encoded, write_csv


def pose_row(index=0, slot=0, sensor="1000000000.000000"):
    values = [
        str(index),
        str(slot),
        sensor,
        "1791010000.000000",
        "0",
        "0",
        "0",
        "1",
        "0",
        "0",
        "0",
        "0.005",
        "normal",
        "100",
        "100",
        "49.5",
        "29.5",
        "100",
        "60",
    ]
    return dict(zip(POSE_HEADER, values, strict=True))


def media():
    return {
        "stream": {"width": 100, "height": 60, "time_base": "1/1000000"},
        "frames": [
            {"best_effort_timestamp": 0, "width": 100, "height": 60},
            {"best_effort_timestamp": 16667, "width": 100, "height": 60},
        ],
        "discarded_packets": [],
        "full_decode": "PASSED",
    }


def fixture(root):
    root.mkdir()
    camera = {
        "enabled": True,
        "media_file": "wide.mp4",
        "index_file": "arkit_pose.csv",
        "schema": POSE_HEADER,
        "world_alignment": "gravity",
    }
    meta = {
        "app": {"name": "com.grape.SensorRecorder", "version": "1.5", "build": "5"},
        "format_version": 1,
        "capture_mode": "arkit",
        "state": "finished",
        "coordinate_conventions": {
            "pose": "T_world_camera (parent_from_child): p_world = R * p_camera + t",
            "recorded_camera": "OpenCV/Rerun RDF: x right, y down, z forward",
            "quaternion_order": "qw,qx,qy,qz",
            "pixel_coordinates": "origin top-left; x right, y down",
            "pixel_orientation": "native",
        },
        "recording_settings": {"arkit_camera": {"max_exposure_duration_sec": 0.005}},
        "streams": {"wide_camera": camera, "arkit_pose": copy.deepcopy(camera)},
    }
    for key, header in STREAM_HEADERS.items():
        meta["streams"][key] = {
            "enabled": key in ["accelerometer", "gyroscope"],
            "file": key + ".csv",
            "schema": header,
            "acceleration_conversion": "CoreMotion g converted to m/s^2 using 9.80665",
        }
    (root / "meta.json").write_text(encoded(meta))
    (root / "wide.mp4").write_bytes(b"fake video for core boundary tests only")
    rows = [pose_row(), pose_row(1, 2, "1000000000.016667")]
    rows[0]["tracking_state"] = "limited"
    rows[1]["tx_m"] = "0.01"
    write_csv(root / "arkit_pose.csv", POSE_HEADER, rows)
    for key in ["accelerometer", "gyroscope"]:
        header = STREAM_HEADERS[key]
        sensors = []
        for t in ["999999999.999990", "1000000000.010000", "1000000000.020000"]:
            r = {k: "0" for k in header}
            r.update(sensor_sec=t, utc_sec="1791010000.0")
            if key == "accelerometer":
                r["az_m_s2"] = "9.80665"
            sensors.append(r)
        write_csv(root / (key + ".csv"), header, sensors)
    (root / "depth").mkdir()
    (root / "depth/0001.bin").write_bytes(b"withheld sensor values")
    (root / "references").mkdir()
    (root / "references/laser.csv").write_text("independent measurements")
    return meta, rows


class FakeVideoInspector:
    """Implements the media port without patching implementation globals."""

    def __init__(self, on_inspect=None):
        self.on_inspect = on_inspect

    def inspect(self, video):
        data = self.on_inspect(video) if self.on_inspect else media()
        return VideoInspection(**data)

    def version(self):
        return "test FFmpeg version"


class FixtureTestCase(unittest.TestCase):
    def run_fixture(self, source, output):
        result = IngestionPipeline(video_inspector=FakeVideoInspector()).run(
            IngestionRequest(source, output)
        )
        return result.manifest, result.report
