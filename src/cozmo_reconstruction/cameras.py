"""Pure optical-camera conversion and native-pixel projection."""

import numpy as np

from cozmo_ingestion.errors import require


def convert_camera(calibration: dict, pose: dict, shift: float) -> dict:
    k = np.asarray(calibration["K"], dtype=float)
    c2w = np.asarray(pose["world_from_camera"], dtype=float)
    require(
        k.shape == (3, 3)
        and c2w.shape == (4, 4)
        and np.isfinite(k).all()
        and np.isfinite(c2w).all(),
        "RECONSTRUCTION_CAMERA_INVALID",
        "Camera dimensions/finite values",
    )
    require(
        np.allclose(k[2], [0, 0, 1], atol=1e-12, rtol=0)
        and k[0, 0] > 0
        and k[1, 1] > 0
        and k[0, 1] == k[1, 0] == 0
        and np.allclose(c2w[3], [0, 0, 0, 1], atol=1e-12, rtol=0)
        and np.allclose(c2w[:3, :3].T @ c2w[:3, :3], np.eye(3), atol=1e-8, rtol=0)
        and abs(np.linalg.det(c2w[:3, :3]) - 1) < 1e-8,
        "RECONSTRUCTION_CAMERA_INVALID",
        "Pinhole/rigid transform contract",
    )
    w2c = np.linalg.inv(c2w)
    require(
        np.allclose(w2c @ c2w, np.eye(4), atol=1e-10, rtol=0),
        "RECONSTRUCTION_PROJECTION_FAILED",
        "Pose inverse",
    )
    backend_k = k.copy()
    backend_k[0, 2] += shift
    backend_k[1, 2] += shift
    return {
        "model": "PINHOLE",
        "image_size": calibration["image_size"],
        "params": [backend_k[0, 0], backend_k[1, 1], backend_k[0, 2], backend_k[1, 2]],
        "K": backend_k.tolist(),
        "camera_from_world": w2c.tolist(),
        "center_m": c2w[:3, 3].tolist(),
        "pixel_convention": "COLMAP top-left pixel center at (0.5, 0.5)",
        "source_center_convention": "UNVERIFIED",
        "principal_point_shift_pixels": shift,
        "distortion": "PINHOLE_APPROXIMATION_UNVERIFIED",
    }


def project(camera: dict, xyz) -> tuple[np.ndarray, float]:
    optical = np.asarray(camera["camera_from_world"]) @ np.r_[xyz, 1.0]
    depth = float(optical[2])
    if abs(depth) < 1e-15:
        return np.array([np.inf, np.inf]), depth
    pixel = np.asarray(camera["K"]) @ optical[:3]
    return pixel[:2] / depth, depth


def select_pairs(mapping: list[dict], policy) -> list[tuple[str, str]]:
    """Small sets exhaustive; larger sets temporal plus bounded pose-compatible revisits."""
    pairs = set()
    for i, a in enumerate(mapping):
        for j in range(i + 1, len(mapping)):
            if len(mapping) <= 24 or j - i <= policy.temporal_window:
                pairs.add((i, j))
        candidates = []
        ta = np.asarray(a["pose"]["world_from_camera"])
        for j in range(i + policy.temporal_window + 1, len(mapping)):
            b = mapping[j]
            if float(b["relative_seconds"]) - float(a["relative_seconds"]) < 2:
                continue
            tb = np.asarray(b["pose"]["world_from_camera"])
            distance = float(np.linalg.norm(ta[:3, 3] - tb[:3, 3]))
            angle = np.degrees(
                np.arccos(np.clip((np.trace(ta[:3, :3].T @ tb[:3, :3]) - 1) / 2, -1, 1))
            )
            if distance < 2 and angle < 40:
                candidates.append((distance, j))
        for _, j in sorted(candidates)[: policy.revisit_neighbors]:
            pairs.add((i, j))
    return [(mapping[i]["image"], mapping[j]["image"]) for i, j in sorted(pairs)]
