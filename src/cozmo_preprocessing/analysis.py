"""Image quality and native sensor diagnostics, without trajectory estimation."""

import bisect
import math

import cv2
import numpy as np


def analysis_gray(image, width: int):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if gray.shape[1] > width:
        gray = cv2.resize(
            gray,
            (width, round(gray.shape[0] * width / gray.shape[1])),
            interpolation=cv2.INTER_AREA,
        )
    return gray


def image_quality(image, width: int) -> dict:
    gray = analysis_gray(image, width)
    corners = cv2.goodFeaturesToTrack(gray, 400, 0.01, 8)
    histogram = cv2.calcHist([gray], [0], None, [32], [0, 256]).ravel()
    histogram /= histogram.sum()
    return {
        "laplacian_variance": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "dark_fraction": float(np.mean(gray < 8)),
        "bright_fraction": float(np.mean(gray > 247)),
        "mean_luminance": float(gray.mean()),
        "texture_corners": 0 if corners is None else len(corners),
        "luminance_histogram": histogram.tolist(),
        "analysis_size": [gray.shape[1], gray.shape[0]],
    }


def score_candidates(candidates: list[dict]):
    reference = max(
        float(np.quantile([c["quality"]["laplacian_variance"] for c in candidates], 0.9)), 1e-6
    )
    previous = None
    for candidate in candidates:
        q = candidate["quality"]
        sharp = min(1.0, math.log1p(q["laplacian_variance"]) / math.log1p(reference))
        texture = min(1.0, q["texture_corners"] / 150)
        exposure = 1 - min(1.0, q["dark_fraction"] + q["bright_fraction"])
        q["score"] = 0.45 * sharp + 0.35 * texture + 0.20 * exposure
        q["sharpness_reference_p90"] = reference
        q["histogram_change_from_previous"] = (
            None
            if previous is None
            else float(np.abs(np.array(q["luminance_histogram"]) - np.array(previous)).sum() / 2)
        )
        previous = q["luminance_histogram"]
        flags = candidate["flags"]
        if q["laplacian_variance"] < reference * 0.15:
            flags.append("RELATIVELY_LOW_SHARPNESS")
        if q["texture_corners"] < 30:
            flags.append("LOW_TEXTURE")
        if q["dark_fraction"] + q["bright_fraction"] > 0.25:
            flags.append("CLIPPED_EXPOSURE")


def pose_delta(first: dict, second: dict) -> tuple[float, float]:
    a, b = np.array(first["world_from_camera"]), np.array(second["world_from_camera"])
    distance = float(np.linalg.norm(b[:3, 3] - a[:3, 3]))
    cosine = float((np.trace(a[:3, :3].T @ b[:3, :3]) - 1) / 2)
    return distance, math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


class SensorIndex:
    """Index independent native samples; never interpolate across boundaries."""

    def __init__(self, samples: list[dict], columns: list[str]):
        self.samples, self.columns = samples, columns
        self.times = [float(row["relative_seconds"]) for row in samples]

    def interval(self, start: float, end: float) -> dict:
        left, right = bisect.bisect_left(self.times, start), bisect.bisect_right(self.times, end)
        rows = self.samples[left:right]
        magnitudes = [math.sqrt(sum(float(row[k]) ** 2 for k in self.columns)) for row in rows]
        return {
            "interval_seconds": [start, end],
            "sample_range": [left, right],
            "sample_count": len(rows),
            "range_convention": "start inclusive, end exclusive native row indices",
            "boundary_covered": bool(
                self.times and self.times[0] <= start and end <= self.times[-1]
            ),
            "first_sample_seconds": self.times[left] if rows else None,
            "last_sample_seconds": self.times[right - 1] if rows else None,
            "rms_magnitude": math.sqrt(sum(v * v for v in magnitudes) / len(rows))
            if rows
            else None,
            "maximum_magnitude": max(magnitudes) if rows else None,
            "interpolation": "NONE",
            "position_integration": "NONE",
        }
