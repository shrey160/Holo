"""Bounded offline comparison with existing pinned proto-1 assets; not default backend.

Run using proto-1's isolated CPU inference environment. Source audit must pass with the
main reconstruction CLI before and after this experiment; all artifact identities are
also checked here. Predicted cameras/pointmaps are diagnostics, never replacement poses.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from cozmo_ingestion import IngestionRequest
from cozmo_ingestion.bundle import BundleTransaction
from cozmo_ingestion.errors import require
from cozmo_ingestion.storage import BundleIntegrity, sha256, write_json
from cozmo_preprocessing.verification import lines

from .analysis import analyze
from .geometry import intrinsics, neighbors
from .models import DensePolicy

CODE_PIN = "3d10cf7a3016fc0f9bb13a071ee66c47b10be0d9"
MODEL_PIN = "00f9c245bbcb60522d1ed7f9e9d88462c6e3f38a"
ENCODER_PIN = "7764ea0f912e53c92e82eb78a2a1631e92725fc8"
DEPTH_SOURCE = "RGB learned predicted Z; source K/pose conditioned; no captured depth or grounding"


def run(sparse: Path, assets: Path, output: Path, ranks: tuple[int, ...]):
    sparse, assets, output = sparse.resolve(), assets.resolve(), output.resolve()
    for source in (sparse, assets):
        require(
            not output.is_relative_to(source) and not source.is_relative_to(output),
            "OUTPUT_SOURCE_OVERLAP",
            str(output),
        )
    manifest = json.loads((sparse / "manifest.json").read_text())
    integrity = BundleIntegrity(sparse, manifest["artifact_sha256"])
    integrity.verify_all()
    mapping = [
        v
        for v in json.loads(integrity.path("input_mapping.json").read_text())
        if v["rank"] in ranks
    ]
    require(
        3 <= len(mapping) == len(ranks) <= 12 and tuple(sorted(set(ranks))) == ranks,
        "LEARNED_SELECTION_INVALID",
        "3..12 unique sparse ranks",
    )
    vendor = assets / "vendor/map-anything"
    revision = subprocess.check_output(
        [
            "git",
            "-c",
            f"safe.directory={vendor.as_posix()}",
            "-C",
            str(vendor),
            "rev-parse",
            "HEAD",
        ],
        text=True,
    ).strip()
    require(revision == CODE_PIN, "LEARNED_ASSET_CHANGED", "Code pin")
    require(
        subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={vendor.as_posix()}",
                "-C",
                str(vendor),
                "diff",
                "--quiet",
                "HEAD",
            ],
            check=False,
        ).returncode
        == 0,
        "LEARNED_ASSET_CHANGED",
        "Modified vendor code",
    )
    model_dir = assets / "models/map-anything-apache"
    encoder = assets / ".cache/torch/hub/facebookresearch_dinov2_main"
    encoder_revision = subprocess.check_output(
        [
            "git",
            "-c",
            f"safe.directory={encoder.as_posix()}",
            "-C",
            str(encoder),
            "rev-parse",
            "HEAD",
        ],
        text=True,
    ).strip()
    require(encoder_revision == ENCODER_PIN, "LEARNED_ASSET_CHANGED", "Encoder pin")
    require(
        subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={encoder.as_posix()}",
                "-C",
                str(encoder),
                "diff",
                "--quiet",
                "HEAD",
            ],
            check=False,
        ).returncode
        == 0,
        "LEARNED_ASSET_CHANGED",
        "Modified encoder code",
    )
    download = json.loads((model_dir / "download-manifest.json").read_text())
    require(download["revision"] == MODEL_PIN, "LEARNED_ASSET_CHANGED", "Checkpoint revision")
    for name, item in download["files"].items():
        require(sha256(model_dir / name) == item["sha256"], "LEARNED_ASSET_CHANGED", name)
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    sys.path.insert(0, str(vendor))
    import torch
    from mapanything.models import MapAnything
    from mapanything.utils.image import preprocess_inputs
    from PIL import Image

    torch.set_num_threads(4)
    torch.manual_seed(7)
    policy = DensePolicy(max_image_size=518)
    names = {v["rank"]: v["image"] for v in mapping}
    points = lines(integrity.path("points.jsonl"))
    schedule = neighbors(points, names, policy.neighbors)
    with BundleTransaction(IngestionRequest(sparse, output), "learned-depth-comparison") as tx:
        stage = tx.stage
        write_json(stage / "input_mapping.json", mapping)
        write_json(stage / "neighbors.json", schedule)
        views = []
        originals = {c["image"]: c for c in json.loads(integrity.path("cameras.json").read_text())}
        for v in mapping:
            source_camera = originals[v["image"]]
            k = intrinsics(source_camera).astype(np.float32)
            k[:2, 2] -= 0.5  # Explicit COLMAP corner-origin -> OpenCV pixel-center hypothesis.
            with Image.open(integrity.path(f"images/{v['image']}")) as source_image:
                image = source_image.convert("RGB")
            views.append(
                {
                    "img": image,
                    "intrinsics": k,
                    "camera_poses": np.linalg.inv(source_camera["camera_from_world"]).astype(
                        np.float32
                    ),
                    "is_metric_scale": True,
                }
            )
        views = preprocess_inputs(views, resolution_set=518, verbose=True)
        config = json.loads((model_dir / "config.json").read_text())
        config["encoder_config"]["disable_torch_compile_for_pe"] = True
        original_hub_load = torch.hub.load

        def local_encoder_load(repo, name, *args, **kwargs):
            require(
                repo in ("facebookresearch/dinov2", "facebookresearch/dinov2:main"),
                "LEARNED_REMOTE_REQUEST",
                repo,
            )
            kwargs["source"] = "local"
            return original_hub_load(str(encoder), name, *args, **kwargs)

        torch.hub.load = local_encoder_load
        print("Load pinned offline checkpoint on CPU", flush=True)
        try:
            model = (
                MapAnything.from_pretrained(
                    str(model_dir),
                    local_files_only=True,
                    strict=True,
                    encoder_config=config["encoder_config"],
                )
                .to(device="cpu", dtype=torch.float32)
                .eval()
            )
        finally:
            torch.hub.load = original_hub_load
        started = time.perf_counter()
        print(f"Infer {len(views)} pose/K-conditioned views; no depth input", flush=True)
        with torch.inference_mode():
            predictions = model.infer(
                views,
                memory_efficient_inference=True,
                minibatch_size=1,
                use_amp=False,
                apply_mask=True,
                mask_edges=True,
                apply_confidence_mask=True,
                confidence_percentile=10,
                ignore_calibration_inputs=False,
                ignore_depth_inputs=True,
                ignore_pose_inputs=False,
                ignore_depth_scale_inputs=True,
                ignore_pose_scale_inputs=False,
            )
        seconds = time.perf_counter() - started
        require(len(predictions) == len(mapping), "LEARNED_OUTPUT_INVALID", "View count")
        cameras, diagnostics = [], []
        for v, view, prediction in zip(mapping, views, predictions, strict=True):
            name = v["image"]
            depth = prediction["depth_z"].detach().float().cpu().numpy()[0].squeeze()
            mask = prediction["mask"].detach().cpu().numpy()[0].reshape(depth.shape) > 0
            depth = np.where(mask & np.isfinite(depth), depth, 0).astype("<f4")
            k = view["intrinsics"].numpy()[0].copy()
            k[:2, 2] += 0.5
            camera = dict(
                originals[name],
                image_size=[depth.shape[1], depth.shape[0]],
                params=[float(k[0, 0]), float(k[1, 1]), float(k[0, 2]), float(k[1, 2])],
            )
            cameras.append(camera)
            rgb = prediction["img_no_norm"].detach().float().cpu().numpy()[0]
            rgb = np.clip(rgb * (255 if rgb.max() <= 1.01 else 1), 0, 255).astype(np.uint8)
            image_path = stage / f"workspace/images/{name}"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            require(cv2.imwrite(str(image_path), rgb[:, :, ::-1]), "LEARNED_RGB_INVALID", name)
            path = stage / f"workspace/stereo/depth_maps/{name}.geometric.bin"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(
                f"{depth.shape[1]}&{depth.shape[0]}&1&".encode() + depth.T.tobytes(order="F")
            )
            diagnostics.append(
                {
                    "image": name,
                    "predicted_pose": prediction["camera_poses"]
                    .detach()
                    .float()
                    .cpu()
                    .numpy()[0]
                    .tolist(),
                    "predicted_K": prediction["intrinsics"]
                    .detach()
                    .float()
                    .cpu()
                    .numpy()[0]
                    .tolist(),
                    "used_pose": "verified source pose, unchanged",
                    "used_K": "provided K transformed by upstream resize/crop; explicit pixel-origin conversion",
                }
            )
        write_json(stage / "cameras.json", cameras)
        report = analyze(stage, policy, points, depth_source=DEPTH_SOURCE)
        write_json(stage / "report.json", report)
        # Independent second pass verifies the saved masks and voxel cloud before publication.
        require(
            report == analyze(stage, policy, points, write=False, depth_source=DEPTH_SOURCE),
            "LEARNED_REPORT_CHANGED",
            "Independent analysis",
        )
        integrity.verify_all()
        write_json(
            stage / "experiment.json",
            {
                "status": "COMPARISON_REQUIRES_REVIEW",
                "source_sparse_manifest_sha256": sha256(sparse / "manifest.json"),
                "code_revision": revision,
                "checkpoint_revision": MODEL_PIN,
                "encoder_revision": encoder_revision,
                "checkpoint_sha256": download["files"]["model.safetensors"]["sha256"],
                "torch": torch.__version__,
                "device": "CPU",
                "inference_seconds": seconds,
                "depth_source": DEPTH_SOURCE,
                "camera_diagnostics": diagnostics,
                "pose_refinement": False,
                "scale_fitting": False,
                "model_scale_accuracy": "UNVERIFIED",
                "artifact_sha256": {
                    p.relative_to(stage).as_posix(): sha256(p)
                    for p in sorted(stage.rglob("*"))
                    if p.is_file()
                },
            },
        )
        tx.publish()
    print(
        json.dumps(
            {"output": str(output), "report": report, "inference_seconds": seconds}, indent=2
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Offline bounded learned comparison using existing pinned proto-1 assets"
    )
    parser.add_argument("sparse", type=Path)
    parser.add_argument("assets", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--ranks", type=int, nargs="+", required=True)
    args = parser.parse_args()
    run(args.sparse, args.assets, args.output, tuple(args.ranks))
