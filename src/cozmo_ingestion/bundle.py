"""Transactional publication and canonical artifact serialization."""

import collections
import json
import os
import platform
import time
import uuid
from pathlib import Path

from .contracts import SCHEMA
from .errors import IngestionError, require
from .models import BundleContent, IngestionRequest, RunMetadata
from .storage import pipeline_fingerprint, sha256, write_csv, write_json, write_lines


class BundleTransaction:
    """Publish once, after all checks; preserve failed staging diagnostics."""

    def __init__(self, request: IngestionRequest, adapter_name: str) -> None:
        self.request = request
        self.adapter_name = adapter_name
        self.stage = request.output.with_name(request.output.name + ".ingest-" + uuid.uuid4().hex)

    def __enter__(self) -> "BundleTransaction":
        source, output = self.request.source, self.request.output
        require(source.is_dir(), "SOURCE_NOT_FOUND", str(source))
        require(not output.exists(), "OUTPUT_EXISTS", str(output))
        require(
            not output.is_relative_to(source) and not source.is_relative_to(output),
            "OUTPUT_SOURCE_OVERLAP",
            str(output),
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        self.stage.mkdir()
        return self

    def publish(self) -> None:
        require(self.stage.is_dir(), "TRANSACTION_NOT_STARTED", str(self.request.output))
        require(not self.request.output.exists(), "OUTPUT_EXISTS", str(self.request.output))
        self.stage.rename(self.request.output)

    def __exit__(self, error_type, error, traceback) -> bool:
        if error is not None and self.stage.exists():
            code = error.code if isinstance(error, IngestionError) else "INGESTION_FAILED"
            write_json(
                self.stage / "validation/report.json",
                {"status": "FAILED", "code": code, "error": str(error), "readiness": False},
            )
            write_json(
                self.stage / "manifest.json",
                {
                    "schema": SCHEMA,
                    "adapter": self.adapter_name,
                    "status": "FAILED",
                    "code": code,
                },
            )
            raise IngestionError(code, f"{error}; diagnostics: {self.stage}") from error
        return False


class BundleWriter:
    """Own on-disk schema; normalization and adapters do not write artifacts."""

    def write(self, stage: Path, content: BundleContent, runtime: RunMetadata) -> tuple[dict, dict]:
        self._write_observations(stage, content)
        self._write_metadata(stage, content)
        report = self._report(content)
        self._write_report(stage, report)
        artifacts = {
            p.relative_to(stage).as_posix(): sha256(p)
            for p in sorted(stage.rglob("*"))
            if p.is_file()
        }
        manifest = self._manifest(content, artifacts)
        write_json(stage / "manifest.json", manifest)
        write_json(
            stage / "runtime.json",
            {
                "elapsed_seconds": time.perf_counter() - runtime.started,
                "python": platform.python_version(),
                "ffmpeg_version": runtime.ffmpeg_version,
                "commands": {
                    "probe": content.video.probe_command,
                    "decode": content.video.decode_command,
                },
                "runtime_excluded_from_deterministic_artifact_hashes": True,
            },
        )
        return manifest, report

    def _write_observations(self, stage: Path, content: BundleContent) -> None:
        observations = content.observations
        frame_rows, calibrations, poses = (
            observations.frames,
            observations.calibration,
            observations.poses,
        )
        meta, annotated = content.capture.metadata, content.annotations
        for key, samples in observations.sensors.items():
            write_csv(stage / "imu" / (key + ".csv"), list(samples[0]), samples)
        write_csv(stage / "frames.csv", list(frame_rows[0]), frame_rows)
        write_lines(stage / "calibration.jsonl", calibrations)
        write_lines(stage / "trajectory/source_poses.jsonl", poses)
        write_json(stage / "source_metadata.json", meta)
        write_json(stage / "annotations.json", annotated)

    def _write_metadata(self, stage: Path, content: BundleContent) -> None:
        source, output, annotations = (
            content.request.source,
            content.request.output,
            content.request.annotations,
        )
        meta, origin = content.capture.metadata, content.capture.origin
        comments, stream_notes = content.capture.camera_comments, content.capture.sensor_comments
        stream_statistics, association = content.observations.stream_statistics, content.association
        before, assets, adapter_name, policy = (
            content.source_hashes,
            content.assets,
            content.adapter_name,
            content.policy,
        )
        width, height = content.video.stream["width"], content.video.stream["height"]
        roots = {"capture": Path(os.path.relpath(source, output)).as_posix()}
        if annotations:
            roots["annotations"] = Path(os.path.relpath(annotations.parent, output)).as_posix()
        write_json(stage / "sources.json", {"root_hints": roots, "assets": assets})
        write_json(
            stage / "cameras.json",
            {
                "wide": {
                    "image_size": [width, height],
                    "calibration": "per-frame",
                    "native_pixels": True,
                    "orientation": meta["coordinate_conventions"]["pixel_orientation"],
                    "camera_IMU_extrinsics": None,
                    "gravity_world": {"up": [0, 1, 0], "evidence": "EXPORTER_DECLARED"},
                    "image_rotation_applied": False,
                }
            },
        )
        write_json(
            stage / "clocks.json",
            {
                "relative_origin_sensor_seconds": str(origin),
                "origin": "first decoded primary RGB observation",
                "source_timestamp_precision": "six decimal places in inspected CSV; no artificial nanosecond precision",
                "media_association": association,
                "IMU_resampling": "NONE",
                "stream_statistics": stream_statistics,
            },
        )
        write_json(
            stage / "provenance.json",
            {
                "camera_comments": comments,
                "stream_comments": stream_notes,
                "source_sha256": before,
                "adapter": adapter_name,
                "policy": policy.to_dict(),
                "original_metadata": "source_metadata.json",
                "units": {
                    "acceleration": "exported m/s^2 retained",
                    "gyroscope": "rad/s retained",
                    "magnetometer": "uT retained",
                },
                "IMU_axes": "source device axes retained; camera extrinsics unverified",
                "source_world": "preserved; no first-camera/room recentering",
            },
        )

    def _report(self, content: BundleContent) -> dict:
        rows, limited = content.capture.camera_rows, content.observations.limited_frames
        association, findings = content.association, content.observations.findings
        return {
            "status": "PASSED_WITH_FINDINGS",
            "frames": len(rows),
            "tracking_states": dict(collections.Counter(r["tracking_state"] for r in rows)),
            "media_association": association,
            "full_video_decode": "PASSED",
            "source_hashes_unchanged": True,
            "frame_selection": "NONE; all frames retained",
            "findings": findings,
            "readiness": {
                "rgb": True,
                "calibrated_posed_rgb": bool(len(rows) - len(limited)),
                "ios_assisted_rgb": True,
                "raw_IMU_VIO": False,
                "RGBD": False,
                "grounding_localization": False,
            },
            "independent_accuracy": "UNVERIFIED",
        }

    def _write_report(self, stage: Path, report: dict) -> None:
        rows, findings = range(report["frames"]), report["findings"]
        write_json(stage / "validation/report.json", report)
        summary = f"# Ingestion validation\n\n{len(rows)} RGB frames matched; complete video decoding passed. Raw source hashes unchanged. All observations retained.\n\n"
        summary += (
            "\n".join(
                "- " + f["code"] + ": " + json.dumps(f["details"], sort_keys=True) for f in findings
            )
            + "\n"
        )
        (stage / "validation/summary.md").write_text(summary, encoding="utf-8", newline="\n")

    def _manifest(self, content: BundleContent, artifacts: dict[str, str]) -> dict:
        capture = content.capture
        rows, meta, tables, streams = (
            capture.camera_rows,
            capture.metadata,
            capture.sensor_rows,
            capture.streams,
        )
        adapter_name, policy, annotated = content.adapter_name, content.policy, content.annotations
        capture_id, source_identity, stream_headers = (
            content.capture_id,
            content.source_identity,
            content.stream_headers,
        )
        return {
            "schema": SCHEMA,
            "adapter": adapter_name,
            "status": "READY_WITH_FINDINGS",
            "capture_id": capture_id,
            "source_identity_sha256": source_identity,
            "source_platform": "ios",
            "app": meta["app"],
            "profile": "ios_assisted_rgb",
            "policy": policy.to_dict(),
            "frame_count": len(rows),
            "artifact_sha256": artifacts,
            "capabilities": {
                "rgb": "AVAILABLE",
                "calibration": "EXPORTER_DECLARED",
                "pose": "EXPORTER_DECLARED",
                **{key: "AVAILABLE" if key in tables else "DISABLED" for key in stream_headers},
                "measured_depth": "EXCLUDED"
                if streams.get("lidar_depth", {}).get("enabled")
                else "DISABLED",
                "grounding_object": annotated["status"],
            },
            "assistance": {
                "supplied_poses": True,
                "IMU": True,
                "human_scale_prior_declared": bool(annotated["reference_objects"]),
                "human_scale_prior_consumed_for_geometry": False,
                "measured_depth_consumed": False,
            },
            "scale": {
                "source": "supplied ARKit metric pose convention",
                "independently_validated": False,
                "correction_applied": False,
            },
            "pipeline_source_sha256": pipeline_fingerprint(),
            "preprocessing": "NOT_RUN",
            "reconstruction": "NOT_RUN",
        }
