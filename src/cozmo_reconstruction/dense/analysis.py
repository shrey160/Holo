"""Independently checked depth masks, voxel averaging and inspectable previews."""

import json
from pathlib import Path

import cv2
import numpy as np

from cozmo_ingestion.errors import require
from cozmo_reconstruction.preview import write_preview

from .geometry import consistent_mask, intrinsics, read_array, voxel_cloud, world_points


def analyze(
    stage: Path,
    policy,
    sparse_points: list[dict],
    write: bool = True,
    depth_source="RGB stereo; no captured depth or grounding",
):
    cameras = {v["image"]: v for v in json.loads((stage / "cameras.json").read_text())}
    schedule = json.loads((stage / "neighbors.json").read_text())
    depths = {}
    for name, camera in cameras.items():
        depth = read_array(stage / f"workspace/stereo/depth_maps/{name}.geometric.bin")
        require(list(depth.shape[::-1]) == camera["image_size"], "DENSE_GRID_CHANGED", name)
        depths[name] = depth
    rows, positions, colors = [], [], []
    for name in sorted(cameras):
        camera = cameras[name]
        valid, accepted, support = consistent_mask(
            depths[name],
            camera,
            [depths[n] for n in schedule[name]],
            [cameras[n] for n in schedule[name]],
            policy,
        )
        # Sparse agreement is a shared-pose diagnostic, not independent dimensional truth.
        sparse_errors = []
        for point in sparse_points:
            if not any(o["rank"] == camera["rank"] for o in point["observations"]):
                continue
            transform = np.array(camera["camera_from_world"])
            p = transform[:3, :3] @ point["xyz_m"] + transform[:3, 3]
            if p[2] <= 0:
                continue
            pixel = intrinsics(camera) @ p
            x, y = np.floor(pixel[:2] / p[2]).astype(int)
            if 0 <= y < valid.shape[0] and 0 <= x < valid.shape[1] and accepted[y, x]:
                sparse_errors.append(abs(float(depths[name][y, x]) - p[2]) / p[2])
        rows.append(
            {
                "image": name,
                "rank": camera["rank"],
                "pixels": valid.size,
                "backend_valid_pixels": int(valid.sum()),
                "accepted_pixels": int(accepted.sum()),
                "accepted_fraction": float(accepted.mean()),
                "rejected_valid_pixels": int((valid & ~accepted).sum()),
                "support_histogram": {
                    str(n): int((valid & (support == n)).sum()) for n in range(policy.neighbors + 1)
                },
                "sparse_samples": len(sparse_errors),
                "sparse_relative_depth_error_median": float(np.median(sparse_errors))
                if sparse_errors
                else None,
                "sparse_relative_depth_error_p90": float(np.percentile(sparse_errors, 90))
                if sparse_errors
                else None,
            }
        )
        rgb = cv2.imread(str(stage / f"workspace/images/{name}"))
        require(rgb is not None and rgb.shape[:2] == valid.shape, "DENSE_RGB_INVALID", name)
        sampling = accepted.copy()
        grid_y, grid_x = np.indices(valid.shape)
        sampling &= (grid_y % policy.sample_stride == 0) & (grid_x % policy.sample_stride == 0)
        ys, xs = np.nonzero(sampling)
        positions.append(world_points(depths[name], camera, xs, ys))
        colors.append(rgb[ys, xs, ::-1])
        if write:
            (stage / "masks").mkdir(exist_ok=True)
            np.savez_compressed(stage / f"masks/{name}.npz", accepted=accepted, support=support)
            # Shared fixed range; black means absent/rejected, not a measured surface.
            scaled = np.clip(depths[name] / 6 * 255, 0, 255)
            colored = cv2.applyColorMap(np.nan_to_num(scaled).astype(np.uint8), cv2.COLORMAP_TURBO)
            colored[~accepted] = 0
            mask_rgb = rgb.copy()
            mask_rgb[~accepted] = (mask_rgb[~accepted] * 0.2).astype(np.uint8)
            panel = np.concatenate((rgb, colored, mask_rgb), axis=1)
            (stage / "previews").mkdir(exist_ok=True)
            require(
                cv2.imwrite(str(stage / f"previews/{name}.jpg"), panel),
                "DENSE_PREVIEW_FAILED",
                name,
            )
        else:
            with np.load(stage / f"masks/{name}.npz") as masks:
                require(
                    np.array_equal(masks["accepted"], accepted)
                    and np.array_equal(masks["support"], support),
                    "DENSE_MASK_CHANGED",
                    name,
                )
    xyz, rgb = voxel_cloud(np.concatenate(positions), np.concatenate(colors), policy.voxel_size)
    cloud = stage / "cloud.npz"
    if write:
        np.savez_compressed(cloud, xyz_m=xyz, rgb=rgb)
        with (stage / "cloud.ply").open("w", encoding="ascii", newline="\n") as stream:
            stream.write(
                f"ply\nformat ascii 1.0\nelement vertex {len(xyz)}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n"
            )
            for point, color in zip(xyz, rgb, strict=True):
                stream.write(
                    " ".join([*(f"{v:.9g}" for v in point), *(str(v) for v in color)]) + "\n"
                )
        # Reuse source-axis geometry preview without pretending this is a floorplan.
        mapping = json.loads((stage / "input_mapping.json").read_text())
        display_points = [
            {"xyz_m": p.tolist(), "rgb": c.tolist()}
            for p, c in zip(
                xyz[:: max(1, len(xyz) // 25000)], rgb[:: max(1, len(xyz) // 25000)], strict=True
            )
        ]
        # Sparse preview expects point-count and simple status fields.
        write_preview(
            stage / "preview.svg",
            mapping,
            display_points,
            {"geometry_signal": "cross-view depth consistency"},
            layer="dense",
        )
    else:
        with np.load(cloud) as stored:
            require(
                stored["xyz_m"].shape == xyz.shape
                and np.allclose(stored["xyz_m"], xyz, atol=1e-10, rtol=1e-12)
                and np.array_equal(stored["rgb"], rgb),
                "DENSE_CLOUD_CHANGED",
                "Recomputed voxel cloud",
            )
    total = sum(v["pixels"] for v in rows)
    accepted = sum(v["accepted_pixels"] for v in rows)
    return {
        "status": "REVIEW_REQUIRED",
        "views": rows,
        "selected_views": len(rows),
        "backend_valid_pixels": sum(v["backend_valid_pixels"] for v in rows),
        "accepted_pixels": accepted,
        "accepted_fraction": accepted / total,
        "sampled_before_voxel": sum(len(p) for p in positions),
        "voxel_points": len(xyz),
        "units": "source ARKit estimated metres",
        "physical_accuracy": "UNVERIFIED",
        "depth_source": depth_source,
        "coverage_scope": "selected image pixels, not whole room area",
        "mesh": "NOT_RUN",
        "floorplan": "NOT_RUN",
    }
