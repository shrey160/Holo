"""Prepare bounded, source-audited inputs for an isolated CUDA worker."""

import json
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

from cozmo_ingestion.bundle import BundleTransaction
from cozmo_ingestion.errors import require
from cozmo_ingestion.models import IngestionRequest
from cozmo_ingestion.storage import BundleIntegrity, sha256, write_json
from cozmo_reconstruction.boundaries.pipeline import guard_output
from cozmo_reconstruction.boundaries.verification import verify_boundaries


def prepare(request, output: Path, points=100000, width=640):
    require(type(points) is int and 1000 <= points <= 200000, "GAUSSIAN_LIMIT", "Point limit")
    require(type(width) is int and 320 <= width <= 960, "GAUSSIAN_LIMIT", "Image width")
    output = output.resolve()
    guard_output(replace(request, output=output))
    require(not output.exists(), "OUTPUT_EXISTS", str(output))
    require(
        not request.output.is_relative_to(output) and not output.is_relative_to(request.output),
        "OUTPUT_SOURCE_OVERLAP",
        str(output),
    )
    audit = verify_boundaries(request.output, request)
    dense = request.surfaces.upstream.output
    identity = sha256(dense / "manifest.json")
    integrity = BundleIntegrity(
        dense, json.loads((dense / "manifest.json").read_text())["artifact_sha256"]
    )
    with np.load(integrity.path("cloud.npz"), allow_pickle=False) as data:
        indices = np.linspace(0, len(data["xyz_m"]) - 1, min(points, len(data["xyz_m"])), dtype=int)
        xyz, rgb = data["xyz_m"][indices], data["rgb"][indices]
    cameras = json.loads(integrity.path("cameras.json").read_text())
    require(10 <= len(cameras) <= 100, "GAUSSIAN_VIEWS", "10..100 source views required")
    records, views, intrinsics = [], [], []
    with BundleTransaction(IngestionRequest(dense.resolve(), output), "gaussian-inputs") as tx:
        (tx.stage / "images").mkdir()
        for index, camera in enumerate(cameras):
            source = integrity.path("workspace/images/" + camera["image"])
            image = cv2.imread(str(source))
            require(image is not None, "GAUSSIAN_IMAGE", camera["image"])
            source_h, source_w = image.shape[:2]
            require([source_w, source_h] == camera["image_size"], "GAUSSIAN_IMAGE", "Grid mismatch")
            height = round(source_h * width / source_w)
            relative = "images/" + camera["image"]
            require(
                cv2.imwrite(
                    str(tx.stage / relative),
                    cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA),
                    [cv2.IMWRITE_JPEG_QUALITY, 95],
                ),
                "GAUSSIAN_IMAGE",
                relative,
            )
            fx, fy, cx, cy = camera["params"]
            intrinsics.append(
                [
                    [fx * width / source_w, 0, cx * width / source_w],
                    [0, fy * height / source_h, cy * height / source_h],
                    [0, 0, 1],
                ]
            )
            views.append(camera["camera_from_world"])
            records.append(
                {
                    "rank": camera["rank"],
                    "image": relative,
                    "source_image_sha256": sha256(source),
                    "split": "validation" if index % 10 == 5 else "train",
                }
            )
        np.savez(
            tx.stage / "inputs.npz",
            xyz=xyz,
            rgb=rgb,
            viewmats=np.asarray(views),
            Ks=np.asarray(intrinsics),
        )
        write_json(tx.stage / "cameras.json", records)
        require(identity == sha256(dense / "manifest.json"), "SOURCE_CHANGED", "Dense manifest")
        integrity.verify_all()
        write_json(
            tx.stage / "manifest.json",
            {
                "schema": "holo-gsplat-inputs-v1",
                "source_audit": audit,
                "dense_manifest_sha256": identity,
                "boundary_manifest_sha256": sha256(request.output / "manifest.json"),
                "input_policy": {
                    "fixed_cameras": True,
                    "scale_normalization": False,
                    "lidar": False,
                    "grounding": False,
                    "validation": "photometric holdout; initialization uses all source views",
                },
                "artifact_sha256": {
                    p.relative_to(tx.stage).as_posix(): sha256(p)
                    for p in tx.stage.rglob("*")
                    if p.is_file()
                },
            },
        )
        tx.publish()
    return {"status": "PREPARED", "views": len(cameras), "initial_gaussians": len(xyz)}
