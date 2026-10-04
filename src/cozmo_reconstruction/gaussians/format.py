"""Standard 32-byte .splat encoding, including rigid covariance orientation."""

import cv2
import numpy as np

from cozmo_ingestion.errors import require


def rotate_quaternions(quats, rotation):
    vector = cv2.Rodrigues(np.asarray(rotation, dtype=float))[0].reshape(3)
    angle = np.linalg.norm(vector)
    axis = vector / angle if angle > 1e-12 else np.zeros(3)
    a = np.r_[np.cos(angle / 2), axis * np.sin(angle / 2)]
    quats = quats / np.linalg.norm(quats, axis=1, keepdims=True)
    w, v = quats[:, :1], quats[:, 1:]
    return np.c_[a[0] * w[:, 0] - v @ a[1:], a[0] * v + w * a[1:] + np.cross(a[1:], v)]


def encode_splats(data, transform):
    count = len(data["means"])
    for key, shape in (
        ("means", (count, 3)),
        ("scales", (count, 3)),
        ("quats", (count, 4)),
        ("colors", (count, 3)),
        ("opacity", (count,)),
    ):
        value = np.asarray(data[key])
        require(value.shape == shape and np.isfinite(value).all(), "GAUSSIAN_INVALID", key)
    require(
        (data["scales"] > 0).all() and (np.linalg.norm(data["quats"], axis=1) > 1e-6).all(),
        "GAUSSIAN_INVALID",
        "Scales/quaternions",
    )
    require(
        ((data["colors"] >= 0) & (data["colors"] <= 1)).all()
        and ((data["opacity"] >= 0) & (data["opacity"] <= 1)).all(),
        "GAUSSIAN_INVALID",
        "RGB/alpha",
    )
    transform = np.asarray(transform)
    require(
        transform.shape == (4, 4)
        and np.isfinite(transform).all()
        and np.allclose(transform[:3, :3] @ transform[:3, :3].T, np.eye(3), atol=1e-6)
        and np.isclose(np.linalg.det(transform[:3, :3]), 1)
        and np.allclose(transform[3], [0, 0, 0, 1]),
        "GAUSSIAN_INVALID",
        "Rigid transform",
    )
    positions = data["means"] @ transform[:3, :3].T + transform[:3, 3]
    quats = rotate_quaternions(data["quats"], transform[:3, :3])
    result = np.empty(
        count,
        dtype=[
            ("position", "<f4", (3,)),
            ("scale", "<f4", (3,)),
            ("rgba", "u1", (4,)),
            ("quaternion", "u1", (4,)),
        ],
    )
    result["position"], result["scale"] = positions, data["scales"]
    result["rgba"] = np.round(np.c_[data["colors"], data["opacity"]] * 255).astype(np.uint8)
    result["quaternion"] = np.round((quats + 1) * 127.5).clip(0, 255).astype(np.uint8)
    return result.tobytes(), positions
