"""Bounded appearance experiment: fixed camera gauge, fixed-count 3D Gaussians."""

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import cv2
import gsplat
import numpy as np
import torch
from gsplat import rasterization
from torch.nn import functional as F


def digest(path):
    with path.open("rb") as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def ssim(a, b):
    a, b = a.permute(0, 3, 1, 2), b.permute(0, 3, 1, 2)
    mean_a, mean_b = F.avg_pool2d(a, 7, 1), F.avg_pool2d(b, 7, 1)
    var_a = F.avg_pool2d(a * a, 7, 1) - mean_a.square()
    var_b = F.avg_pool2d(b * b, 7, 1) - mean_b.square()
    covariance = F.avg_pool2d(a * b, 7, 1) - mean_a * mean_b
    return (
        ((2 * mean_a * mean_b + 0.01**2) * (2 * covariance + 0.03**2))
        / ((mean_a.square() + mean_b.square() + 0.01**2) * (var_a + var_b + 0.03**2))
    ).mean()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--steps", type=int, default=3000)
    parser.add_argument("--deadline", type=int, default=900)
    args = parser.parse_args()
    if not 1 <= args.steps <= 10000 or not 1 <= args.deadline <= 1800:
        raise ValueError("Bounded steps/deadline required")
    if args.output.exists() or args.output.resolve().is_relative_to(args.inputs.resolve()):
        raise ValueError("Output must be a new separate folder")
    manifest = json.loads((args.inputs / "manifest.json").read_text())
    for name, expected in manifest["artifact_sha256"].items():
        path = (args.inputs / name).resolve()
        if not path.is_relative_to(args.inputs.resolve()) or digest(path) != expected:
            raise ValueError(f"Changed input: {name}")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU required")
    torch.manual_seed(42)
    np.random.seed(42)
    torch.set_num_threads(4)
    args.output.mkdir(parents=True)
    started = time.perf_counter()
    data = np.load(args.inputs / "inputs.npz", allow_pickle=False)

    def tensor(a):
        return torch.tensor(a, dtype=torch.float32, device="cuda")

    xyz, rgb = tensor(data["xyz"]), tensor(data["rgb"] / 255.0)
    count = len(xyz)
    parameters = torch.nn.ParameterDict(
        {
            "means": torch.nn.Parameter(xyz),
            "scales": torch.nn.Parameter(torch.full((count, 3), math.log(0.018), device="cuda")),
            "quats": torch.nn.Parameter(tensor(np.tile([1, 0, 0, 0], (count, 1)))),
            "opacity": torch.nn.Parameter(torch.full((count,), -0.85, device="cuda")),
            "colors": torch.nn.Parameter(torch.logit(rgb.clamp(0.01, 0.99))),
        }
    )
    rates = {"means": 0.00008, "scales": 0.003, "quats": 0.001, "opacity": 0.025, "colors": 0.015}
    optimizer = torch.optim.Adam(
        [{"params": [value], "lr": rates[key]} for key, value in parameters.items()]
    )
    views, intrinsics = tensor(data["viewmats"]), tensor(data["Ks"])
    records = json.loads((args.inputs / "cameras.json").read_text())
    images = [
        tensor(cv2.cvtColor(cv2.imread(str(args.inputs / r["image"])), cv2.COLOR_BGR2RGB) / 255.0)[
            None
        ]
        for r in records
    ]
    height, width = images[0].shape[1:3]
    train = [i for i, r in enumerate(records) if r["split"] == "train"]
    validation = [i for i, r in enumerate(records) if r["split"] == "validation"]

    def render(index):
        return rasterization(
            parameters["means"],
            parameters["quats"],
            parameters["scales"].exp(),
            parameters["opacity"].sigmoid(),
            parameters["colors"].sigmoid(),
            views[index : index + 1],
            intrinsics[index : index + 1],
            width,
            height,
            packed=True,
            near_plane=0.1,
            far_plane=20.0,
            # The pinned packed rasterizer uses its default black background.
            render_mode="RGB",
        )

    @torch.no_grad()
    def evaluate(prefix):
        rows = []
        for index in validation:
            rendered, alpha, _ = render(index)
            mse = (rendered - images[index]).square().mean().item()
            rows.append(
                {
                    "rank": records[index]["rank"],
                    "psnr_db": -10 * math.log10(max(mse, 1e-12)),
                    "ssim": ssim(rendered, images[index]).item(),
                    "opacity_coverage_gt_05": (alpha > 0.5).float().mean().item(),
                }
            )
            pair = torch.cat([images[index][0], rendered[0]], dim=1)
            cv2.imwrite(
                str(args.output / f"{prefix}-{records[index]['rank']:06d}.jpg"),
                cv2.cvtColor(
                    (pair.clamp(0, 1).cpu().numpy() * 255).astype(np.uint8), cv2.COLOR_RGB2BGR
                ),
            )
        return rows

    baseline = evaluate("initial")
    rng = np.random.default_rng(42)
    for step in range(args.steps):
        if time.perf_counter() - started > args.deadline:
            raise TimeoutError("Training deadline exceeded; partial files retained")
        index = train[int(rng.integers(len(train)))]
        rendered, _, _ = render(index)
        loss = 0.8 * F.l1_loss(rendered, images[index]) + 0.2 * (1 - ssim(rendered, images[index]))
        if not torch.isfinite(loss):
            raise RuntimeError("Non-finite training loss")
        loss.backward()
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
        with torch.no_grad():
            parameters["scales"].clamp_(math.log(0.002), math.log(0.15))
            parameters["opacity"].clamp_(-8, 8)
            parameters["quats"].copy_(F.normalize(parameters["quats"], dim=-1))
        if step % 100 == 0:
            print(
                json.dumps(
                    {"step": step, "loss": loss.item(), "seconds": time.perf_counter() - started}
                ),
                flush=True,
            )
    final = evaluate("final")
    for name, expected in manifest["artifact_sha256"].items():
        if digest(args.inputs / name) != expected:
            raise ValueError(f"Input changed during training: {name}")
    torch.cuda.synchronize()
    export = {
        "means": parameters["means"],
        "scales": parameters["scales"].exp(),
        "quats": F.normalize(parameters["quats"], dim=-1),
        "opacity": parameters["opacity"].sigmoid(),
        "colors": parameters["colors"].sigmoid(),
    }
    np.savez(
        args.output / "gaussians.npz",
        **{key: value.detach().cpu().numpy() for key, value in export.items()},
    )
    report = {
        "status": "EXPERIMENT_COMPLETE",
        "steps": args.steps,
        "gaussians": count,
        "elapsed_seconds": time.perf_counter() - started,
        "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
        "gpu": torch.cuda.get_device_name(),
        "torch": torch.__version__,
        "gsplat": gsplat.__version__,
        "cuda": torch.version.cuda,
        "train_views": len(train),
        "validation_views": len(validation),
        "validation_scope": "Photometric holdout only; dense initialization uses all source views",
        "initial": baseline,
        "final": final,
        "pose_optimization": False,
        "scale_normalization": False,
        "sh_degree": 0,
        "densification": False,
        "physical_accuracy": "UNVERIFIED",
        "inputs_manifest_sha256": digest(args.inputs / "manifest.json"),
        "worker_sha256": digest(Path(__file__)),
    }
    save_json(args.output / "report.json", report)
    save_json(
        args.output / "manifest.json",
        {
            "schema": "holo-gsplat-trial-v1",
            "artifact_sha256": {p.name: digest(p) for p in args.output.iterdir() if p.is_file()},
        },
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
