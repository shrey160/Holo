"""Validated canonical-reader API with explicit input roles; not an OS sandbox."""

import csv
import json
from pathlib import Path

from .adapters.sensor_recorder import ADAPTER
from .contracts import SCHEMA
from .errors import require
from .storage import BundleIntegrity, inside, sha256

ROLE_ALLOWLIST = {
    "video_rgb": {"rgb"},
    "ios_assisted_rgb": {
        "rgb",
        "metadata",
        "pose_calibration",
        "accelerometer",
        "gyroscope",
        "device_motion",
        "magnetometer",
        "user_scale_prior",
    },
    "evaluation": {
        "rgb",
        "metadata",
        "pose_calibration",
        "accelerometer",
        "gyroscope",
        "device_motion",
        "magnetometer",
        "user_scale_prior",
        "measured_depth_excluded",
        "evaluation_reference",
    },
}
ARTIFACTS = {
    "frames": "frames.csv",
    "calibration": "calibration.jsonl",
    "poses": "trajectory/source_poses.jsonl",
    "accelerometer": "imu/accelerometer.csv",
    "gyroscope": "imu/gyroscope.csv",
    "device_motion": "imu/device_motion.csv",
    "magnetometer": "imu/magnetometer.csv",
    "annotations": "annotations.json",
}


class CaptureReader:
    """Read admitted observations with integrity checks and an access log."""

    def __init__(
        self,
        folder: str | Path,
        profile: str = "ios_assisted_rgb",
        source_root: str | Path | None = None,
    ) -> None:
        self.folder = Path(folder).resolve()
        require(profile in ROLE_ALLOWLIST, "UNKNOWN_PROFILE", profile)
        self.profile = profile
        self.manifest = json.loads((self.folder / "manifest.json").read_text(encoding="utf-8"))
        require(
            self.manifest.get("status") == "READY_WITH_FINDINGS"
            and self.manifest.get("schema") == SCHEMA
            and self.manifest.get("adapter") == ADAPTER,
            "CAPTURE_NOT_READY",
            str(folder),
        )
        self.hashes = self.manifest["artifact_sha256"]
        for required in [
            "sources.json",
            "frames.csv",
            "calibration.jsonl",
            "trajectory/source_poses.jsonl",
            "annotations.json",
        ]:
            require(required in self.hashes, "MISSING_ARTIFACT", required)
        self.integrity = BundleIntegrity(self.folder, self.hashes)
        self.consumed = []
        source_data = json.loads(self.integrity.path("sources.json").read_text(encoding="utf-8"))
        self.assets = {a["id"]: a for a in source_data["assets"]}
        require(len(self.assets) == len(source_data["assets"]), "DUPLICATE_ASSET", "sources.json")
        self.roots = {
            key: (self.folder / hint.replace("\\", "/")).resolve()
            for key, hint in source_data["root_hints"].items()
        }
        if source_root is not None:
            self.roots["capture"] = Path(source_root).resolve()

    def verify_bundle(self) -> int:
        return self.integrity.verify_all()

    def read_source(self, asset_id: str) -> bytes:
        require(asset_id in self.assets, "UNKNOWN_ASSET", asset_id)
        asset = self.assets[asset_id]
        require(asset["role"] in ROLE_ALLOWLIST[self.profile], "INPUT_ROLE_DENIED", asset["role"])
        path = inside(self.roots[asset["root"]], asset["path"])
        require(path.is_file() and sha256(path) == asset["sha256"], "SOURCE_CHANGED", asset_id)
        self.consumed.append({"asset_id": asset_id, "role": asset["role"]})
        return path.read_bytes()

    def records(self, kind: str) -> list[dict] | dict:
        require(kind in ARTIFACTS, "UNKNOWN_RECORD_KIND", kind)
        require(self.profile != "video_rgb" or kind == "frames", "INPUT_ROLE_DENIED", kind)
        path = self.integrity.path(ARTIFACTS[kind])
        self.consumed.append({"artifact": ARTIFACTS[kind]})
        if path.suffix == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        if path.suffix == ".jsonl":
            return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        if self.profile == "video_rgb":
            allowed = {
                "frame_id",
                "camera_id",
                "video_asset_id",
                "decoded_rank",
                "media_pts_ticks",
                "media_timebase",
                "decoded_status",
            }
            rows = [{key: value for key, value in row.items() if key in allowed} for row in rows]
        return rows

    def usage(self) -> dict:
        return {
            "profile": self.profile,
            "consumed": list(self.consumed),
            "boundary": "API role allowlist; external code must use this reader rather than arbitrary file IO",
        }
