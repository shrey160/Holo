"""Pixel-center-aware stereo tests; no pose fitting or scale correction."""

from collections import Counter
from itertools import combinations
from pathlib import Path

import numpy as np

from cozmo_ingestion.errors import require


def read_array(path: Path) -> np.ndarray:
    """COLMAP little-endian float32 array: width&height&channels&, Fortran payload."""
    with path.open("rb") as stream:
        header = bytearray()
        while header.count(b"&") < 3:
            byte = stream.read(1)
            require(bool(byte) and len(header) < 100, "DENSE_ARRAY_INVALID", str(path))
            header.extend(byte)
        width, height, channels = map(int, header[:-1].split(b"&"))
        require(
            0 < width <= 1920 and 0 < height <= 1920 and channels in (1, 3),
            "DENSE_ARRAY_INVALID",
            str(path),
        )
        values = np.frombuffer(stream.read(), dtype="<f4")
    require(values.size == width * height * channels, "DENSE_ARRAY_INVALID", str(path))
    array = values.reshape((width, height, channels), order="F").transpose(1, 0, 2)
    return array[..., 0] if channels == 1 else array


def neighbors(points: list[dict], names: dict[int, str], count: int) -> dict[str, list[str]]:
    shared = Counter()
    for point in points:
        ranks = sorted({o["rank"] for o in point["observations"]} & names.keys())
        shared.update(combinations(ranks, 2))
    result = {}
    for rank, name in names.items():
        scores = [(shared[tuple(sorted((rank, other)))], other) for other in names if other != rank]
        ranked = sorted(scores, key=lambda v: (-v[0], v[1]))
        result[name] = [names[r] for score, r in ranked[:count] if score > 0]
        require(len(result[name]) >= 2, "DENSE_OVERLAP_INSUFFICIENT", str(rank))
    return result


def intrinsics(camera: dict) -> np.ndarray:
    fx, fy, cx, cy = camera["params"]
    return np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=float)


def world_points(depth: np.ndarray, camera: dict, xs: np.ndarray, ys: np.ndarray):
    # COLMAP uses the top-left corner as origin: pixel centers are x+0.5/y+0.5.
    pixels = np.column_stack((xs + 0.5, ys + 0.5, np.ones(len(xs))))
    optical = (pixels @ np.linalg.inv(intrinsics(camera)).T) * depth[ys, xs, None]
    inverse = np.linalg.inv(np.asarray(camera["camera_from_world"]))
    return optical @ inverse[:3, :3].T + inverse[:3, 3]


def resample_depth(depth, source_camera, target_camera):
    """Nearest sample of optical Z on a new grid with the same physical camera pose.

    Coordinates follow each actual K, including any declared resize/crop. Depth is
    neither scaled nor filled. Intended for a controlled diagnostic comparison.
    """
    import cv2

    require(
        np.allclose(
            source_camera["camera_from_world"],
            target_camera["camera_from_world"],
            atol=1e-10,
            rtol=0,
        ),
        "DENSE_POSE_CHANGED",
        "Resampling requires the same camera pose",
    )
    width, height = target_camera["image_size"]
    ys, xs = np.indices((height, width))
    rays = (
        np.stack((xs + 0.5, ys + 0.5, np.ones_like(xs)), axis=-1)
        @ np.linalg.inv(intrinsics(target_camera)).T
    )
    pixels = rays @ intrinsics(source_camera).T
    uv = pixels[..., :2] / pixels[..., 2:]
    return cv2.remap(
        depth,
        (uv[..., 0] - 0.5).astype(np.float32),
        (uv[..., 1] - 0.5).astype(np.float32),
        cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )


def consistent_mask(depth, camera, other_depths, other_cameras, policy):
    valid = np.isfinite(depth) & (depth >= policy.min_depth) & (depth <= policy.max_depth)
    ys, xs = np.nonzero(valid)
    xyz = world_points(depth, camera, xs, ys)
    support = np.zeros(depth.shape, dtype=np.uint8)
    counts = np.zeros(len(xs), dtype=np.uint8)
    own = np.asarray(camera["camera_from_world"])
    center = np.asarray(camera["center_m"])
    own_ray = xyz - center
    own_norm = np.linalg.norm(own_ray, axis=1)
    for target, target_camera in zip(other_depths, other_cameras, strict=True):
        transform = np.asarray(target_camera["camera_from_world"])
        optical = xyz @ transform[:3, :3].T + transform[:3, 3]
        z = optical[:, 2]
        projected = optical @ intrinsics(target_camera).T
        uv = projected[:, :2] / np.where(z > 0, z, 1)[:, None]
        finite = np.all(np.isfinite(uv), axis=1)
        # Bound before integer conversion, including points behind the camera.
        inside = finite & (z > 0) & (uv[:, 0] >= 0) & (uv[:, 0] < target.shape[1])
        inside &= (uv[:, 1] >= 0) & (uv[:, 1] < target.shape[0])
        indices = np.flatnonzero(inside)
        tx, ty = np.floor(uv[inside]).astype(int).T
        observed = target[ty, tx]
        good = (
            np.isfinite(observed) & (observed >= policy.min_depth) & (observed <= policy.max_depth)
        )
        good &= np.abs(observed - z[inside]) <= policy.relative_depth_error * z[inside]
        back_xyz = world_points(target, target_camera, tx, ty)
        back_optical = back_xyz @ own[:3, :3].T + own[:3, 3]
        back_z = back_optical[:, 2]
        back_pixels = back_optical @ intrinsics(camera).T
        back_uv = back_pixels[:, :2] / np.where(back_z > 0, back_z, 1)[:, None]
        residual = np.linalg.norm(
            back_uv - np.column_stack((xs[inside] + 0.5, ys[inside] + 0.5)), axis=1
        )
        good &= (back_z > 0) & (residual <= policy.roundtrip_pixels)
        ray = xyz[inside] - np.asarray(target_camera["center_m"])
        denominator = np.linalg.norm(ray, axis=1) * own_norm[inside]
        cosine = np.sum(ray * own_ray[inside], axis=1) / np.maximum(denominator, 1e-15)
        angle = np.rad2deg(np.arccos(np.clip(cosine, -1, 1)))
        good &= angle >= policy.min_angle_degrees
        counts[indices[good]] += 1
    support[ys, xs] = counts
    return valid, support >= policy.min_support, support


def voxel_cloud(xyz, rgb, size):
    if len(xyz) == 0:
        return xyz, rgb
    cells = np.floor(xyz / size).astype(np.int64)
    _, index, inverse = np.unique(cells, axis=0, return_index=True, return_inverse=True)
    counts = np.bincount(inverse)
    positions = np.stack(
        [np.bincount(inverse, weights=xyz[:, i]) / counts for i in range(3)], axis=1
    )
    colors = np.stack([np.bincount(inverse, weights=rgb[:, i]) / counts for i in range(3)], axis=1)
    return positions, np.rint(colors).astype(np.uint8)
