"""Restricted prepared-input boundary; audit sources without admitting reference geometry."""

import json
from dataclasses import dataclass

from cozmo_ingestion import CaptureReader
from cozmo_ingestion.errors import require
from cozmo_ingestion.storage import BundleIntegrity, sha256
from cozmo_ingestion.verification import verify
from cozmo_preprocessing.verification import lines, verify_preprocessing

from .models import ReconstructionPolicy, ReconstructionRequest


@dataclass
class PreparedInput:
    request: ReconstructionRequest
    policy: ReconstructionPolicy

    def __post_init__(self):
        self.prepared = self.request.prepared.resolve()
        self.bundle = self.request.bundle.resolve()
        reader = CaptureReader(self.bundle, "ios_preprocessing", self.request.source_root)
        self.source = reader.roots["capture"]
        self.audit()
        self.manifest = json.loads((self.prepared / "manifest.json").read_text(encoding="utf-8"))
        self.integrity = BundleIntegrity(self.prepared, self.manifest["artifact_sha256"])
        views = lines(self.integrity.path("views.jsonl"))
        self.all_ranks = [v["rank"] for v in views]
        selected = self.request.ranks if self.request.ranks is not None else tuple(self.all_ranks)
        require(
            all(type(r) is int for r in selected)
            and tuple(sorted(set(selected))) == selected
            and 3 <= len(selected) <= self.policy.max_views
            and set(selected).issubset(self.all_ranks),
            "RECONSTRUCTION_SELECTION_INVALID",
            "Require 3..max_views unique ascending prepared ranks",
        )
        ks = {r["id"]: r for r in lines(self.integrity.path("calibration.jsonl"))}
        poses = {r["id"]: r for r in lines(self.integrity.path("poses.jsonl"))}
        self.mapping = [
            {
                "rank": v["rank"],
                "frame_id": v["frame_id"],
                "relative_seconds": v["relative_seconds"],
                "image": f"{v['rank']:06d}.jpg",
                "prepared_image": v["image"],
                "image_sha256": sha256(self.integrity.path(v["image"])),
                "calibration": ks[v["calibration_id"]],
                "pose": poses[v["pose_id"]],
                "flags": v["flags"],
                "gyro_motion": v["gyro_motion"],
            }
            for v in views
            if v["rank"] in selected
        ]
        self.snapshot = self.identity()

    def identity(self):
        return {
            "prepared_manifest_sha256": sha256(self.prepared / "manifest.json"),
            "ingestion_manifest_sha256": sha256(self.bundle / "manifest.json"),
        }

    def audit(self):
        self.source_audit = verify(self.bundle, self.source)
        self.prepared_audit = verify_preprocessing(self.prepared, self.bundle, self.source)

    def recheck(self):
        require(
            self.identity() == self.snapshot, "RECONSTRUCTION_SOURCE_CHANGED", "Source manifests"
        )
        self.audit()
