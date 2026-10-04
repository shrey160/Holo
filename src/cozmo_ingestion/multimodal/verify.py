"""Independent verification of a canonical-capture-2 photo bundle.

Verification works from the portable bundle alone. When the original source folder is
supplied it additionally re-hashes the originals and re-inspects native dimensions and
EXIF orientation, proving source preservation without mutating anything.
"""

from pathlib import Path

from ..errors import require
from ..storage import sha256
from .media import DefaultImageInspector
from .reader import MultimodalCaptureReader


def verify_v2(
    folder: str | Path,
    source: str | Path | None = None,
    replay: str | Path | None = None,
) -> dict:
    reader = MultimodalCaptureReader(folder)
    count = reader.verify_bundle()
    require(
        reader.verification["status"] == "PASSED",
        "VERIFICATION_NOT_PASSED",
        "Stored verification report is not PASSED",
    )
    inspector = DefaultImageInspector()
    originals_verified = 0
    if source is not None:
        root = Path(source).resolve()
        for asset in reader.assets():
            for relative in asset["source_paths"]:
                path = (root / relative).resolve()
                require(path.is_file(), "SOURCE_NOT_FOUND", relative)
                require(sha256(path) == asset["sha256"], "SOURCE_CHANGED", relative)
                if asset["media_format"] in {"jpeg", "png"}:
                    inspection = inspector.inspect(path)
                    require(
                        inspection.width == asset["width_px"]
                        and inspection.height == asset["height_px"],
                        "SOURCE_DIMENSIONS_CHANGED",
                        relative,
                    )
                    require(
                        inspection.orientation == asset.get("orientation"),
                        "SOURCE_ORIENTATION_CHANGED",
                        relative,
                    )
                originals_verified += 1
    replay_equal = None
    if replay is not None:
        other = MultimodalCaptureReader(replay)
        other.verify_bundle()
        require(
            reader.manifest == other.manifest,
            "NONDETERMINISTIC_REPLAY",
            "Manifest identities differ",
        )
        replay_equal = True
    return {
        "status": "PASSED",
        "schema": reader.manifest["schema"],
        "mode": reader.modality,
        "artifacts_verified": count,
        "assets_verified": len(reader.assets()),
        "observations_verified": len(reader.observations),
        "originals_reverified": originals_verified,
        "portable_bundle_verified": True,
        "scale_applied": reader.references()["scale_applied"],
        "deterministic_replay_equal": replay_equal,
        "independent_accuracy": "UNVERIFIED",
    }
