"""Deterministic canonical-capture-2 serialization and atomic publication."""

import platform
import shutil
import time
from pathlib import Path

from ..errors import require
from ..storage import sha256, write_json, write_lines
from .models import CaptureBundleContent

ARTIFACTS_EXCLUDED_FROM_HASHES = {"manifest.json", "runtime.json"}


class MultimodalBundleWriter:
    """Own the v2 layout; adapters and pipelines never write artifacts themselves."""

    def write(self, stage: Path, content: CaptureBundleContent, runtime) -> tuple[dict, dict]:
        write_json(stage / "rooms.json", content.rooms_doc)
        write_json(stage / "assets.json", content.assets_doc)
        write_lines(stage / "observations.jsonl", content.observations)
        write_lines(stage / "associations.jsonl", content.associations)
        write_lines(stage / "calibration.jsonl", content.calibrations)
        write_lines(stage / "poses.jsonl", content.poses)
        write_json(stage / "references.json", content.references_doc)
        write_json(stage / "verification.json", content.verification)
        for source_path, absolute in content.copies:
            target = stage / "sources" / source_path
            target.parent.mkdir(parents=True, exist_ok=True)
            require(not target.exists(), "DUPLICATE_SOURCE_PATH", source_path)
            shutil.copyfile(absolute, target)
        artifacts = {
            path.relative_to(stage).as_posix(): sha256(path)
            for path in sorted(stage.rglob("*"))
            if path.is_file() and path.name not in ARTIFACTS_EXCLUDED_FROM_HASHES
        }
        manifest = {**content.manifest_base, "artifact_sha256": artifacts}
        write_json(stage / "manifest.json", manifest)
        write_json(
            stage / "runtime.json",
            {
                "elapsed_seconds": time.perf_counter() - runtime["started"],
                "python": platform.python_version(),
                "image_inspector": runtime["inspector"],
                "runtime_excluded_from_deterministic_artifact_hashes": True,
            },
        )
        return manifest, content.verification
