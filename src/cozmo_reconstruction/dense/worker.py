"""Isolated pinned CUDA backend; source model/images are read-only inputs."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pycolmap as pc

from cozmo_ingestion.errors import require
from cozmo_ingestion.storage import sha256, write_json
from cozmo_reconstruction.colmap import camera_records

from .models import DensePolicy
from .runtime import executable_path, runtime_status


def run(stage: Path, sparse: Path):
    runtime = runtime_status()
    require(runtime["available"], "DENSE_CUDA_UNAVAILABLE", str(runtime["reason"]))
    policy = DensePolicy(**json.loads((stage / "policy.json").read_text()))
    mapping = json.loads((stage / "input_mapping.json").read_text())
    schedule = json.loads((stage / "neighbors.json").read_text())
    started = time.perf_counter()
    workspace = stage / "workspace"
    options = pc.UndistortCameraOptions()
    options.max_image_size = policy.max_image_size
    pc.undistort_images(
        workspace,
        sparse / "model",
        sparse / "images",
        image_names=[v["image"] for v in mapping],
        undistort_options=options,
        num_threads=policy.threads,
    )
    model = pc.Reconstruction(workspace / "sparse")
    by_name = {v["image"]: v for v in mapping}
    # Some COLMAP versions retain nonselected model cameras; only selected images enter stereo.
    records = camera_records(
        model, {v["image"]: v for v in json.loads((sparse / "input_mapping.json").read_text())}
    )
    records = [r for r in records if r["image"] in by_name]
    require(len(records) == len(mapping), "DENSE_CAMERA_IDENTITY", "Selected undistorted images")
    original = {c["image"]: c for c in json.loads((sparse / "cameras.json").read_text())}
    for record in records:
        before = original[record["image"]]
        require(
            np.allclose(
                record["camera_from_world"], before["camera_from_world"], atol=1e-10, rtol=0
            ),
            "DENSE_POSE_CHANGED",
            record["image"],
        )
        scale = np.array(record["image_size"]) / before["image_size"]
        expected = np.array(before["params"]) * scale[[0, 1, 0, 1]]
        require(
            record["model"] == "PINHOLE"
            and np.allclose(record["params"], expected, atol=1e-8, rtol=0),
            "DENSE_GRID_CHANGED",
            record["image"],
        )
        record["source_image_size"] = before["image_size"]
        record["source_params"] = before["params"]
        record["scale_xy"] = scale.tolist()
    write_json(stage / "cameras.json", records)
    config = workspace / "stereo/patch-match.cfg"
    config.write_text(
        "".join(f"{name}\n{', '.join(targets)}\n" for name, targets in schedule.items())
    )
    patch = pc.PatchMatchOptions()
    patch.max_image_size = policy.max_image_size
    patch.gpu_index = "0"
    patch.num_threads = policy.threads
    patch.num_iterations = policy.iterations
    patch.cache_size = 2
    patch.filter_min_triangulation_angle = policy.min_angle_degrees
    patch.filter_min_num_consistent = policy.min_support
    patch.write_consistency_graph = False
    print(f"PatchMatch {len(mapping)} views, grid {policy.max_image_size}, GPU 0", flush=True)
    executable_hash = None
    if runtime["backend"] == "pycolmap_cuda":
        pc.patch_match_stereo(workspace, options=patch)
    else:
        executable = executable_path()
        executable_hash = sha256(executable)
        command = [
            str(executable),
            "patch_match_stereo",
            "--workspace_path",
            str(workspace),
            "--log_target",
            "stdout",
        ]
        # Match the Python worker's pinned policy; shell interpretation is never used.
        for name in (
            "max_image_size",
            "gpu_index",
            "num_threads",
            "num_iterations",
            "cache_size",
            "filter_min_triangulation_angle",
            "filter_min_num_consistent",
            "write_consistency_graph",
        ):
            value = getattr(patch, name)
            command.extend(
                [
                    f"--PatchMatchStereo.{name}",
                    str(int(value) if isinstance(value, bool) else value),
                ]
            )
        subprocess.run(
            command,
            check=True,
            stdout=sys.stdout,
            stderr=sys.stderr,
            **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
        )
        require(
            sha256(executable) == executable_hash,
            "DENSE_BACKEND_CHANGED",
            "Executable changed during inference",
        )
    write_json(
        stage / "backend.json",
        {
            "name": "COLMAP CUDA PatchMatch",
            "version": pc.__version__,
            "has_cuda": True,
            "invocation": runtime["backend"],
            "executable_sha256": executable_hash,
            "depth_source": "RGB multi-view stereo",
            "depth_convention": "optical camera Z",
            "seconds": time.perf_counter() - started,
            "options": patch.todict(),
            "undistortion": "source PINHOLE, uniform corner-origin K scaling; no crop or pose change",
        },
    )


if __name__ == "__main__":
    run(Path(sys.argv[1]), Path(sys.argv[2]))
