"""Application service coordinating derived views, diagnostics and atomic publication."""

import hashlib
import platform
import shutil
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from cozmo_ingestion import CaptureReader, IngestionRequest
from cozmo_ingestion.adapters.sensor_recorder import ADAPTER
from cozmo_ingestion.bundle import BundleTransaction
from cozmo_ingestion.errors import require
from cozmo_ingestion.storage import encoded, sha256, write_csv, write_json, write_lines

from .analysis import SensorIndex, image_quality, pose_delta, score_candidates
from .matching import ViewMatcher
from .media import FFmpegFrameDecoder, save_jpeg
from .models import PreprocessingPolicy, PreprocessingRequest
from .selection import candidate_indices, choose_views

SCHEMA = "holo-preprocessing-v1"
INPUT_POLICY = {
    "profile": "ios_preprocessing",
    "admitted": [
        "RGB",
        "per-frame intrinsics",
        "source ARKit poses",
        "independent accelerometer",
        "independent gyroscope",
    ],
    "excluded": [
        "depth",
        "confidence",
        "reference dimensions",
        "reference photo",
        "magnetometer",
        "fused device motion",
        "evaluation references",
    ],
    "grounding_applied": False,
    "scale_applied": False,
    "pose_refinement": "NONE",
}


def source_fingerprint():
    root = Path(__file__).parent
    sources = {
        p.name: hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest()
        for p in sorted(root.glob("*.py"))
    }
    return hashlib.sha256(encoded(sources).encode()).hexdigest()


class PreprocessingPipeline:
    def __init__(self, policy: PreprocessingPolicy | None = None, decoder=None):
        self.policy = policy or PreprocessingPolicy()
        self.decoder = decoder or FFmpegFrameDecoder()

    def run(self, request: PreprocessingRequest) -> dict:
        bundle, output = request.bundle.resolve(), request.output.resolve()
        reader = CaptureReader(bundle, "ios_preprocessing", request.source_root)
        require(
            reader.manifest["adapter"] == ADAPTER,
            "PREPROCESS_SOURCE_UNSUPPORTED",
            "This version prepares inspected Sensor Recorder iOS captures only",
        )
        reader.verify_bundle()
        video = reader.source_path("wide.mp4")
        reader.source_path("arkit_pose.csv")
        require(
            not output.is_relative_to(video.parent) and not video.parent.is_relative_to(output),
            "OUTPUT_SOURCE_OVERLAP",
            str(output),
        )
        frames = reader.records("frames")
        calibration = reader.records("calibration")
        poses = reader.records("poses")
        require(
            0 < len(frames) <= self.policy.max_frames, "PREPROCESS_FRAME_LIMIT", str(len(frames))
        )
        ks, ts = {r["id"]: r for r in calibration}, {r["id"]: r for r in poses}
        require(
            len(ks) == len(ts) == len(frames),
            "PREPROCESS_ASSOCIATION_FAILED",
            "Calibration/pose count",
        )
        require(
            all(
                int(f["decoded_rank"]) == i and f["frame_id"] in ks and f["frame_id"] in ts
                for i, f in enumerate(frames)
            ),
            "PREPROCESS_ASSOCIATION_FAILED",
            "Frame identity",
        )
        sensors, indices = {}, {}
        for name, columns in {
            "accelerometer": ["ax_m_s2", "ay_m_s2", "az_m_s2"],
            "gyroscope": ["gx_rad_s", "gy_rad_s", "gz_rad_s"],
        }.items():
            require(
                reader.manifest["capabilities"][name] == "AVAILABLE",
                "PREPROCESS_IMU_REQUIRED",
                name,
            )
            sensors[name] = reader.records(name)
            reader.source_path(f"{name}.csv")
            indices[name] = SensorIndex(sensors[name], columns)
        ranks = candidate_indices(frames, self.policy.candidate_fps)
        require(
            len(ranks) <= self.policy.max_candidates, "PREPROCESS_CANDIDATE_LIMIT", str(len(ranks))
        )
        size = calibration[0]["image_size"]
        require(
            0 < size[0] * size[1] <= 8_000_000,
            "PREPROCESS_PIXEL_LIMIT",
            "Maximum 8 million native pixels per frame",
        )
        require(
            all(k["image_size"] == size for k in calibration),
            "PREPROCESS_GRID_CHANGED",
            "Native grid must remain constant",
        )
        events = []
        for a, b in zip(frames, frames[1:], strict=False):
            distance, _ = pose_delta(ts[a["frame_id"]], ts[b["frame_id"]])
            elapsed = float(b["relative_seconds"]) - float(a["relative_seconds"])
            if distance / elapsed > self.policy.pose_speed_warning_m_s:
                events.append(
                    {
                        "first_rank": int(a["decoded_rank"]),
                        "second_rank": int(b["decoded_rank"]),
                        "seconds": float(b["relative_seconds"]),
                        "speed_m_s": distance / elapsed,
                        "diagnosis": "UNVERIFIED",
                    }
                )
        original_hash = sha256(video)
        transaction_request = IngestionRequest(bundle, output)
        with BundleTransaction(transaction_request, SCHEMA) as transaction:
            stage = transaction.stage
            temporary_images = stage / "candidate-images"
            candidates = []
            for rank, image in self.decoder.candidates(video, frames, ranks, size):
                require(
                    rank in ranks and image.shape == (size[1], size[0], 3),
                    "PREPROCESS_PIXEL_ASSOCIATION_FAILED",
                    str(rank),
                )
                f = frames[rank]
                quality = image_quality(image, self.policy.analysis_width)
                normal = f["tracking_state"] == "normal"
                c = {
                    "rank": rank,
                    "frame_id": f["frame_id"],
                    "seconds": float(f["relative_seconds"]),
                    "tracking_normal": normal,
                    "quality": quality,
                    "flags": [] if normal else ["NON_NORMAL_TRACKING"],
                }
                c["gyro_motion"] = indices["gyroscope"].interval(
                    max(0, c["seconds"] - 0.125), c["seconds"] + 0.125
                )
                if (c["gyro_motion"]["maximum_magnitude"] or 0) > self.policy.gyro_warning_rad_s:
                    c["flags"].append("FAST_DEVICE_ROTATION")
                if any(e["first_rank"] <= rank <= e["second_rank"] for e in events):
                    c["flags"].append("POSE_SPEED_WARNING")
                candidates.append(c)
                save_jpeg(temporary_images / f"{rank:06d}.jpg", image)
                thumb = cv2.resize(
                    image,
                    (320, round(image.shape[0] * 320 / image.shape[1])),
                    interpolation=cv2.INTER_AREA,
                )
                save_jpeg(stage / "thumbnails" / f"{rank:06d}.jpg", thumb)
            require(
                [c["rank"] for c in candidates] == ranks,
                "PREPROCESS_DECODE_ASSOCIATION_FAILED",
                "Candidate identities",
            )
            score_candidates(candidates)
            chosen = choose_views(candidates, ts, self.policy)
            # Retain observations around quality events for review; never silently bridge pose jumps.
            for event in events:
                for rank in ranks:
                    if abs(float(frames[rank]["relative_seconds"]) - event["seconds"]) <= 0.5:
                        chosen.setdefault(rank, []).append("POSE_EVENT_CONTEXT")
            matcher = ViewMatcher(temporary_images, ks, ts, self.policy)
            lookup = {c["rank"]: c for c in candidates}
            selected = sorted(chosen)
            pairs = [
                matcher.pair(lookup[a], lookup[b])
                for a, b in zip(selected, selected[1:], strict=False)
            ]
            # One bounded recovery pass adds intervening native candidates to weak links.
            for pair in pairs:
                if pair["visual_link"] == "WEAK":
                    for rank in ranks:
                        if pair["first_rank"] < rank < pair["second_rank"]:
                            chosen.setdefault(rank, []).append("WEAK_LINK_RECOVERY")
            selected = sorted(chosen)
            pairs = [
                matcher.pair(lookup[a], lookup[b])
                for a, b in zip(selected, selected[1:], strict=False)
            ]
            weak = [p for p in pairs if p["visual_link"] == "WEAK"]
            temporal_gaps = [
                p for p in pairs if p["time_gap_seconds"] > self.policy.max_gap_seconds
            ]
            low_parallax = bool(pairs) and sum(p["low_baseline"] for p in pairs) / len(pairs) > 0.8
            selected_records, imu_intervals = [], []
            previous_seconds = float(frames[0]["relative_seconds"])
            for rank in selected:
                c, f = lookup[rank], frames[rank]
                name = f"images/{rank:06d}.jpg"
                (stage / "images").mkdir(exist_ok=True)
                shutil.copyfile(temporary_images / f"{rank:06d}.jpg", stage / name)
                selected_records.append(
                    {
                        "rank": rank,
                        "frame_id": f["frame_id"],
                        "source_frame_index": int(f["source_frame_index"]),
                        "media_pts_ticks": f["media_pts_ticks"],
                        "media_timebase": f["media_timebase"],
                        "sensor_seconds": f["sensor_seconds"],
                        "relative_seconds": f["relative_seconds"],
                        "calibration_id": f["calibration_id"],
                        "pose_id": f["pose_id"],
                        "image": name,
                        "thumbnail": f"thumbnails/{rank:06d}.jpg",
                        "image_size": size,
                        "pixel_transform": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                        "encoding": "JPEG quality 95 from decoded native BGR pixels; lossy, no geometric transform",
                        "tracking_state": f["tracking_state"],
                        "quality": c["quality"],
                        "flags": c["flags"],
                        "gyro_motion": c["gyro_motion"],
                        "selection_reasons": sorted(set(chosen[rank])),
                    }
                )
                imu_intervals.append(
                    {
                        "frame_id": f["frame_id"],
                        **{
                            name: index.interval(previous_seconds, c["seconds"])
                            for name, index in indices.items()
                        },
                    }
                )
                previous_seconds = c["seconds"]
            for c in candidates:
                c["selected"] = c["rank"] in chosen
                c["selection_reasons"] = sorted(set(chosen.get(c["rank"], [])))
            write_lines(stage / "candidates.jsonl", candidates)
            write_lines(stage / "views.jsonl", selected_records)
            write_lines(stage / "calibration.jsonl", [ks[lookup[r]["frame_id"]] for r in selected])
            write_lines(stage / "poses.jsonl", [ts[lookup[r]["frame_id"]] for r in selected])
            write_lines(stage / "imu_intervals.jsonl", imu_intervals)
            write_lines(stage / "pairs.jsonl", pairs)
            for name, rows in sensors.items():
                write_csv(stage / "imu" / f"{name}.csv", list(rows[0]), rows)
            report = {
                "schema": SCHEMA,
                "status": "PREPARED_WITH_FINDINGS",
                "source_frame_count": len(frames),
                "candidate_count": len(candidates),
                "selected_count": len(selected),
                "supported_links": len(pairs) - len(weak),
                "weak_links": weak,
                "temporal_components": len(weak) + 1,
                "component_definition": "breaks in adjacent selected image support; not rooms or global match-graph components",
                "maximum_selected_gap_seconds": max(
                    (p["time_gap_seconds"] for p in pairs), default=0
                ),
                "low_baseline_links": sum(p["low_baseline"] for p in pairs),
                "temporal_gaps": temporal_gaps,
                "limited_source_frames": [
                    int(f["decoded_rank"]) for f in frames if f["tracking_state"] != "normal"
                ],
                "pose_speed_events": events,
                "input_policy": INPUT_POLICY,
                "readiness": "REVIEW_REQUIRED"
                if weak or events or temporal_gaps or low_parallax
                else "READY_FOR_RECONSTRUCTION_TRIAL",
                "metric_accuracy": "UNVERIFIED; source metre scale retained without external correction",
                "doorway_coverage": "MANUAL_REVIEW_REQUIRED; bounded temporal coverage, no doorway detector or room labels",
                "calibration": "native per-frame K; distortion unverified; no undistortion",
                "synchronization": "source clock association; physical RGB/IMU latency and camera/IMU extrinsics unverified",
                "previews": [
                    {
                        "rank": r,
                        "seconds": lookup[r]["seconds"],
                        "score": lookup[r]["quality"]["score"],
                        "flags": lookup[r]["flags"],
                    }
                    for r in selected
                ],
            }
            write_json(stage / "report.json", report)
            write_json(stage / "usage.json", reader.usage())
            # No candidate deletion touches user data; this directory belongs to this staging run.
            shutil.rmtree(temporary_images)
            require(sha256(video) == original_hash, "SOURCE_CHANGED", video.name)
            reader.verify_bundle()
            for asset in ("arkit_pose.csv", "accelerometer.csv", "gyroscope.csv"):
                reader.source_path(asset)
            manifest = {
                "schema": SCHEMA,
                "status": "PREPARED_WITH_FINDINGS",
                "input_policy": INPUT_POLICY,
                "source_capture_id": reader.manifest["capture_id"],
                "source_manifest_sha256": sha256(bundle / "manifest.json"),
                "source_video_sha256": original_hash,
                "policy": asdict(self.policy),
                "pipeline_sha256": source_fingerprint(),
                "artifact_sha256": {
                    p.relative_to(stage).as_posix(): sha256(p)
                    for p in sorted(stage.rglob("*"))
                    if p.is_file()
                },
                "tools": {
                    "python": platform.python_version(),
                    "opencv": cv2.__version__,
                    "numpy": np.__version__,
                    "ffmpeg": self.decoder.version,
                },
            }
            write_json(stage / "manifest.json", manifest)
            transaction.publish()
        return report
