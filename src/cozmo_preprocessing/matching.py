"""SIFT links with independent image geometry and supplied-pose consistency diagnostics."""

import cv2
import numpy as np

from .analysis import analysis_gray, pose_delta
from .media import read_image
from .models import PreprocessingPolicy


class ViewMatcher:
    def __init__(self, images, calibrations: dict, poses: dict, policy: PreprocessingPolicy):
        self.images, self.calibrations, self.poses, self.policy = (
            images,
            calibrations,
            poses,
            policy,
        )
        self.cache = {}
        self.sift = cv2.SIFT_create(nfeatures=1200)
        self.matcher = cv2.BFMatcher(cv2.NORM_L2)

    def features(self, c):
        rank = c["rank"]
        if rank not in self.cache:
            image = read_image(self.images / f"{rank:06d}.jpg")
            gray = analysis_gray(image, self.policy.analysis_width)
            points, descriptors = self.sift.detectAndCompute(gray, None)
            # Match coordinates on original native grid, with resize pixel-center correction.
            sx, sy = image.shape[1] / gray.shape[1], image.shape[0] / gray.shape[0]
            xy = np.array(
                [[(p.pt[0] + 0.5) * sx - 0.5, (p.pt[1] + 0.5) * sy - 0.5] for p in points],
                dtype=np.float64,
            )
            self.cache[rank] = (xy, descriptors)
        return self.cache[rank]

    def pair(self, a: dict, b: dict) -> dict:
        pa, da = self.features(a)
        pb, db = self.features(b)
        good = (
            []
            if da is None or db is None or len(db) < 2
            else [
                matches[0]
                for matches in self.matcher.knnMatch(da, db, k=2)
                if len(matches) == 2 and matches[0].distance < 0.75 * matches[1].distance
            ]
        )
        # Unique target features prevent repeated texture from inflating support.
        unique = {}
        for match in sorted(good, key=lambda m: m.distance):
            unique.setdefault(match.trainIdx, match)
        good = list(unique.values())
        xa = np.array([pa[m.queryIdx] for m in good])
        xb = np.array([pb[m.trainIdx] for m in good])
        inliers, h_inliers, mask = 0, 0, None
        if len(good) >= 8:
            cv2.setRNGSeed(0)
            _, mask = cv2.findFundamentalMat(xa, xb, cv2.FM_RANSAC, 3.0, 0.999)
            inliers = int(mask.sum()) if mask is not None else 0
        if len(good) >= 4:
            cv2.setRNGSeed(0)
            _, hm = cv2.findHomography(xa, xb, cv2.RANSAC, 3.0)
            h_inliers = int(hm.sum()) if hm is not None else 0
        support = max(inliers, h_inliers)
        linked = (
            support >= self.policy.min_matches
            and support / max(1, len(good)) >= self.policy.min_inlier_ratio
        )
        distance, angle = pose_delta(self.poses[a["frame_id"]], self.poses[b["frame_id"]])
        residual = None
        if distance > 1e-5 and len(good) >= 8:
            ta = np.array(self.poses[a["frame_id"]]["world_from_camera"])
            tb = np.array(self.poses[b["frame_id"]]["world_from_camera"])
            relative = np.linalg.inv(tb) @ ta
            x, y, z = relative[:3, 3]
            cross = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
            ka = np.array(self.calibrations[a["frame_id"]]["K"])
            kb = np.array(self.calibrations[b["frame_id"]]["K"])
            fundamental = np.linalg.inv(kb).T @ cross @ relative[:3, :3] @ np.linalg.inv(ka)
            ua = np.column_stack([xa, np.ones(len(xa))])
            ub = np.column_stack([xb, np.ones(len(xb))])
            la, lb = ua @ fundamental.T, ub @ fundamental
            numerator = np.sum(ub * la, axis=1) ** 2
            denominator = la[:, 0] ** 2 + la[:, 1] ** 2 + lb[:, 0] ** 2 + lb[:, 1] ** 2
            errors = np.sqrt(numerator / np.maximum(denominator, 1e-20))
            # Report against independently estimated F inliers where available.
            used = errors[mask.ravel().astype(bool)] if mask is not None and inliers else errors
            residual = float(np.median(used))
        return {
            "first_rank": a["rank"],
            "second_rank": b["rank"],
            "first_frame_id": a["frame_id"],
            "second_frame_id": b["frame_id"],
            "time_gap_seconds": b["seconds"] - a["seconds"],
            "ratio_matches": len(good),
            "fundamental_inliers": inliers,
            "homography_inliers": h_inliers,
            "visual_link": "SUPPORTED" if linked else "WEAK",
            "translation_m": distance,
            "rotation_degrees": angle,
            "low_baseline": distance < 0.02,
            "supplied_pose_median_sampson_pixels": residual,
            "geometry": "image support only; homography may represent a plane or pure rotation; no triangulation",
        }
