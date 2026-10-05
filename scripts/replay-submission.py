"""Recompute baseline/fixed room numbers from a hash-bound native RGB stereo cache."""

import argparse
import json
import time
from pathlib import Path

import numpy as np

from cozmo_ingestion.storage import BundleIntegrity, sha256, write_json
from cozmo_reconstruction.viewer.ceiling import estimate_ceiling
from cozmo_reconstruction.viewer.dense_automatic import dense_room
from cozmo_reconstruction.viewer.rough_room import complete_rough_room, rough_room_svg


def replay(root, output):
    cache = root / "submission/reproduction/cache"
    provenance = json.loads((cache / "provenance.json").read_text(encoding="utf-8"))
    BundleIntegrity(cache, provenance["artifact_sha256"]).verify_all()
    raw = root / "example_data/video/single_room.zip"
    if sha256(raw) != provenance["raw_zip_sha256"]:
        raise ValueError("Example input changed")
    if output.exists():
        raise ValueError("Use a new replay output directory")
    with np.load(cache / "native-room.npz", allow_pickle=False) as cloud:
        xyz, labels, rgb = cloud["xyz_m"], cloud["plane_index"], cloud["rgb"]
    planes = json.loads((cache / "planes.json").read_text(encoding="utf-8"))
    cameras = json.loads((cache / "cameras.json").read_text(encoding="utf-8"))
    started = time.monotonic()
    positions, path, frame, fixed, extra = dense_room(xyz, labels, planes, cameras)
    baseline = complete_rough_room(extra["candidate_spans"], [], path[:, [0, 2]] * [1, -1])
    baseline["ceiling_estimate"] = estimate_ceiling(positions, baseline)
    _, _, repeat_frame, repeat, _ = dense_room(xyz, labels, planes, cameras)
    reference = json.loads((root / "docs/regressions/native-dense-2026-10-04/fix/comparison.json").read_text(encoding="utf-8"))
    for name, room in (("before", baseline), ("after", fixed)):
        np.testing.assert_allclose(room["dimensions_estimated_m"], reference[name]["dimensions_estimated_m"], atol=1e-9, rtol=0)
        np.testing.assert_allclose(room["area_estimated_m2"], reference[name]["area_estimated_m2"], atol=1e-9, rtol=0)
        np.testing.assert_allclose(room["ceiling_estimate"]["height_estimated_m"], reference[f"ceiling_{name}_m"], atol=1e-9, rtol=0)
    if fixed != repeat or frame != repeat_frame or len(rgb) != len(xyz):
        raise ValueError("Cache replay is not deterministic in this runtime")
    output.mkdir(parents=True)
    for name, room in (("before", baseline), ("after", fixed)):
        write_json(output / f"{name}.json", room)
        (output / f"{name}.svg").write_text(rough_room_svg(room, []), encoding="utf-8", newline="\n")
    summary = {
        "status": "PASSED", "path": "CACHED_ROOM_STAGE; not new stereo inference",
        "raw_zip_sha256": provenance["raw_zip_sha256"], "source_points": len(xyz),
        "stereo_views": len(cameras), "replay_seconds": time.monotonic() - started,
        "before_dimensions_m": baseline["dimensions_estimated_m"],
        "after_dimensions_m": fixed["dimensions_estimated_m"],
        "before_area_m2": baseline["area_estimated_m2"], "after_area_m2": fixed["area_estimated_m2"],
        "before_ceiling_m": baseline["ceiling_estimate"]["height_estimated_m"],
        "after_ceiling_m": fixed["ceiling_estimate"]["height_estimated_m"],
        "same_cache_repeats": 2, "software_repeat_max_dimension_delta_m": 0.0,
        "independent_capture_repeatability": "NOT_RUN", "physical_accuracy": "UNVERIFIED",
    }
    write_json(output / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    replay(Path(__file__).resolve().parents[1], args.output.resolve())
