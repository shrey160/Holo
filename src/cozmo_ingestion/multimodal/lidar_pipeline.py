"""Application service for canonical-capture-2 LiDAR (raw-depth) ingestion.

Raw depth/confidence are retained with explicit, unverified convention provenance.
No reconstruction, fusion, axis flip or unit conversion is performed.
"""

import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Protocol

from ..bundle import BundleTransaction
from ..contracts import DEFAULT_POLICY, IngestionPolicy
from ..errors import require
from ..media import find_ffmpeg
from ..models import IngestionResult
from ..numeric import integer
from ..storage import pipeline_fingerprint, sha256
from .adapters.stray_lidar import (
    ADAPTER,
    CONVENTION_EVIDENCE,
    SOURCE_FORMAT,
    StrayLidarSource,
    load,
)
from .bundle import MultimodalBundleWriter
from .contracts import (
    CAPABILITY_ABSENT,
    CAPABILITY_PRESENT_UNVERIFIED,
    CAPABILITY_VERIFIED_FORMAT,
    MODE_LIDAR,
    SCHEMA_V2,
    MultimodalRequest,
)
from .depth import decode_png_gray, png_gray_header
from .models import CaptureBundleContent
from .schema import validate_bundle_documents

LIDAR_LIMITATIONS = [
    "Depth units, definition and confidence meaning are FORMAT_REFERENCE_ASSUMED, not verified.",
    "Exporter identity/version and physical camera registration remain unknown.",
    "No RGB-to-depth axis flip or unit conversion is applied; raw values are preserved.",
    "Depth/pose fusion, calibration resolution and reconstruction are NOT_IMPLEMENTED_FOR_MODALITY.",
]


class RgbProbe(Protocol):
    def probe(self, clip: Path) -> dict: ...


class FFmpegRgbProbe:
    def __init__(self, executable: str | Path | None = None) -> None:
        self.executable = executable

    def probe(self, clip: Path) -> dict:
        ffmpeg, ffprobe = find_ffmpeg(self.executable)
        command = [
            str(ffprobe),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_frames",
            "-show_entries",
            "stream=width,height,codec_name,nb_read_frames",
            "-of",
            "json",
            str(clip),
        ]
        probe = subprocess.run(command, capture_output=True, text=True)
        require(
            probe.returncode == 0 and not probe.stderr.strip(),
            "VIDEO_PROBE_FAILED",
            probe.stderr,
        )
        streams = json.loads(probe.stdout).get("streams", [])
        require(len(streams) == 1, "EMPTY_OR_AMBIGUOUS_VIDEO", clip.name)
        stream = streams[0]
        return {
            "width": int(stream["width"]),
            "height": int(stream["height"]),
            "codec": stream.get("codec_name", "unknown"),
            "frame_count": int(stream.get("nb_read_frames") or 0),
        }


def _sample_indices(ids: list[int], limit: int) -> set[int]:
    if len(ids) <= limit:
        return set(ids)
    step = max(1, len(ids) // limit)
    sampled = set(ids[::step])
    sampled.add(ids[-1])
    return sampled


class LiDARIngestionPipeline:
    def __init__(
        self,
        rgb_probe: RgbProbe | None = None,
        writer: MultimodalBundleWriter | None = None,
        policy: IngestionPolicy = DEFAULT_POLICY,
        sample_frames: int = 24,
    ) -> None:
        self.rgb_probe = rgb_probe if rgb_probe is not None else FFmpegRgbProbe()
        self.writer = writer if writer is not None else MultimodalBundleWriter()
        self.policy = policy
        self.sample_frames = sample_frames

    def run(self, request: MultimodalRequest) -> IngestionResult:
        require(request.mode == MODE_LIDAR, "NOT_IMPLEMENTED_FOR_MODALITY", str(request.mode))
        source = Path(request.source).resolve()
        request = MultimodalRequest(
            source,
            Path(request.output).resolve(),
            MODE_LIDAR,
            request.source_format or SOURCE_FORMAT,
        )
        src = load(source)
        rgb = self.rgb_probe.probe(src.rgb)
        started = time.perf_counter()
        with BundleTransaction(request, ADAPTER, schema=SCHEMA_V2) as transaction:
            findings = _lidar_findings(src, rgb, self.sample_frames)
            assets, copies = _source_assets(src)
            (
                depth_grid,
                confidence_grid,
                depth_stats,
                confidence_stats,
                depth_assets,
                conf_assets,
            ) = _inspect_depth(src, self.sample_frames)
            assets.extend(depth_assets)
            assets.extend(conf_assets)
            copies.extend(_frame_copies(src))
            calibrations, poses, observations = _frame_records(src, rgb, depth_grid)
            depth_assets_by_native = {int(a["id"].rsplit("-", 1)[1]): a["id"] for a in depth_assets}
            confidence_assets_by_native = {
                int(a["id"].rsplit("-", 1)[1]): a["id"] for a in conf_assets
            }
            for row in observations:
                native = int(row["native_frame_id"])
                row["asset_id"] = depth_assets_by_native[native]
                row["depth_asset_id"] = depth_assets_by_native[native]
                row["confidence_asset_id"] = confidence_assets_by_native.get(native)
            capabilities = _capabilities(src)
            readiness = {
                "ingestion_integrity": "PASSED",
                "tier_profile": "LIDAR_RAW_DEPTH",
                "conventions": "CONVENTIONS_UNVERIFIED",
                "consumer_readiness": {
                    "preprocessing": "NOT_IMPLEMENTED_FOR_MODALITY",
                    "reconstruction": "NOT_IMPLEMENTED_FOR_MODALITY",
                },
                "metric_accuracy": "UNVERIFIED",
            }
            conventions = _conventions(rgb, depth_grid, confidence_grid)
            verification = {
                "status": "PASSED",
                "integrity": "PASSED",
                "profile": "LIDAR_RAW_DEPTH",
                "capabilities": capabilities,
                "readiness": readiness,
                "findings": findings,
                "independent_accuracy": "UNVERIFIED",
                "assets": len(assets),
                "observations": len(observations),
                "rooms": 1,
                "conventions": conventions,
                "streams": {
                    "camera_records": len(src.odometry),
                    "depth_frames": len(src.depth),
                    "confidence_frames": len(src.confidence),
                    "rgb_decoded_frames": rgb["frame_count"],
                    "unassociated_native_frame_ids": [0],
                },
                "depth_samples": depth_stats,
                "confidence_samples": confidence_stats,
                "geometry_readiness": "CONVENTIONS_UNVERIFIED",
            }
            identity = _source_identity(assets)
            property_id = "property-" + identity[:16]
            rooms_doc = {
                "property_id": property_id,
                "membership": "UNSEGMENTED",
                "rooms": [
                    {
                        "id": "room-1",
                        "label": "Unsegmented LiDAR capture",
                        "source_path": ".",
                        "declared_connection_ids": [],
                        "image_count": len(observations),
                    }
                ],
                "declared_connections": [],
            }
            assets_doc = {"assets": assets}
            references_doc = {"scale_applied": False, "objects": []}
            associations = [
                {
                    "id": "assoc-rgb-native",
                    "kind": "rgb_to_native",
                    "method": "decoded RGB rank i -> odometry frame i+1 (one initial discard)",
                    "unassociated_native_frame_ids": [0],
                    "rgb_decoded_frames": rgb["frame_count"],
                    "camera_records": len(src.odometry),
                    "physical_synchronization": "UNVERIFIED",
                }
            ]
            validate_bundle_documents(
                rooms_doc,
                assets_doc,
                observations,
                references_doc,
                associations,
                calibrations,
                poses,
            )
            manifest_base = {
                "schema": SCHEMA_V2,
                "capture_id": "lidar-" + identity[:16],
                "mode": MODE_LIDAR,
                "source_format": request.source_format,
                "adapter": ADAPTER,
                "status": "READY_WITH_FINDINGS",
                "policy": self.policy.to_dict(),
                "property_id": property_id,
                "room_count": 1,
                "image_count": len(observations),
                "distinct_image_count": len(assets),
                "source_identity_sha256": identity,
                "frame_count": len(src.odometry),
                "depth_frame_count": len(src.depth),
                "confidence_frame_count": len(src.confidence),
                "rgb_frame_count": rgb["frame_count"],
                "depth_grid": depth_grid,
                "intrinsics_reference_grid": [rgb["width"], rgb["height"]],
                "scale": {
                    "source": "exporter pose convention (unverified)",
                    "independently_validated": False,
                    "correction_applied": False,
                },
                "capabilities": capabilities,
                "readiness": readiness,
                "conventions": conventions,
                "profile": "LIDAR_RAW_DEPTH",
                "preprocessing": "NOT_IMPLEMENTED_FOR_MODALITY",
                "reconstruction": "NOT_IMPLEMENTED_FOR_MODALITY",
                "pipeline_source_sha256": pipeline_fingerprint(),
                "limitations": LIDAR_LIMITATIONS,
            }
            content = CaptureBundleContent(
                request=request,
                manifest_base=manifest_base,
                rooms_doc=rooms_doc,
                assets_doc=assets_doc,
                observations=observations,
                associations=associations,
                references_doc=references_doc,
                verification=verification,
                copies=tuple(copies),
                calibrations=calibrations,
                poses=poses,
            )
            runtime = {"started": started, "inspector": type(self.rgb_probe).__name__}
            manifest, report = self.writer.write(transaction.stage, content, runtime)
            _assert_sources_unchanged(assets, source)
            transaction.publish()
        return IngestionResult(manifest, report, request.output)


def _source_assets(src: StrayLidarSource) -> tuple[list[dict], list[tuple[str, Path]]]:
    assets, copies = [], []
    entries = [
        ("asset-rgb", "walkthrough_rgb", "video", "rgb.mp4", {"room_ids": ["room-1"]}),
        ("asset-odometry", "pose_calibration", "csv", "odometry.csv", {"room_ids": []}),
        ("asset-camera-matrix", "pose_calibration", "csv", "camera_matrix.csv", {"room_ids": []}),
        ("asset-imu", "imu_native", "csv", "imu.csv", {"room_ids": []}),
    ]
    for asset_id, role, media, name, extra in entries:
        path = src.root / name
        assets.append(
            {
                "id": asset_id,
                "role": role,
                "media_format": media,
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
                "source_paths": [name],
                **extra,
            }
        )
        copies.append((name, path))
    return assets, copies


def _frame_copies(src: StrayLidarSource) -> list[tuple[str, Path]]:
    copies = []
    for path in sorted(src.depth.values()) + sorted(src.confidence.values()):
        copies.append((path.relative_to(src.root).as_posix(), path))
    return copies


def _inspect_depth(src, sample_frames):
    depth_grid = confidence_grid = None
    depth_assets, conf_assets = [], []
    sampled = _sample_indices(sorted(src.depth), sample_frames)
    depth_invalid = 0
    depth_min = depth_max = None
    confidence_counts: dict[str, int] = {}
    for native in sorted(src.depth):
        path = src.depth[native]
        data = path.read_bytes()
        info = png_gray_header(data)
        require(info["bit_depth"] == 16, "DEPTH_ENCODING_MISMATCH", f"frame {native}")
        grid = [info["width"], info["height"]]
        if depth_grid is None:
            depth_grid = grid
        else:
            require(grid == depth_grid, "DEPTH_GRID_MISMATCH", f"frame {native}")
        depth_assets.append(
            {
                "id": f"asset-depth-{native:06d}",
                "role": "lidar_depth",
                "media_format": "png",
                "width_px": info["width"],
                "height_px": info["height"],
                "decode": "STRUCTURE_VERIFIED",
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "source_paths": [path.relative_to(src.root).as_posix()],
                "room_ids": ["room-1"],
            }
        )
        if native in sampled:
            _, _, _, values = decode_png_gray(data)
            for value in values:
                if value == 0:
                    depth_invalid += 1
                else:
                    depth_min = value if depth_min is None else min(depth_min, value)
                    depth_max = value if depth_max is None else max(depth_max, value)
    if confidence_grid is not None and depth_grid is not None:
        require(confidence_grid == depth_grid, "CONFIDENCE_GRID_MISMATCH", "grids differ")
    for native in sorted(src.confidence):
        path = src.confidence[native]
        data = path.read_bytes()
        info = png_gray_header(data)
        require(info["bit_depth"] == 8, "CONFIDENCE_ENCODING_MISMATCH", f"frame {native}")
        grid = [info["width"], info["height"]]
        if confidence_grid is None:
            confidence_grid = grid
        else:
            require(grid == confidence_grid, "CONFIDENCE_GRID_MISMATCH", f"frame {native}")
        require(depth_grid is None or grid == depth_grid, "CONFIDENCE_GRID_MISMATCH", str(native))
        conf_assets.append(
            {
                "id": f"asset-conf-{native:06d}",
                "role": "confidence",
                "media_format": "png",
                "width_px": info["width"],
                "height_px": info["height"],
                "decode": "STRUCTURE_VERIFIED",
                "sha256": hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "source_paths": [path.relative_to(src.root).as_posix()],
                "room_ids": ["room-1"],
            }
        )
        if native in sampled:
            _, _, _, values = decode_png_gray(data)
            for value in values:
                confidence_counts[str(value)] = confidence_counts.get(str(value), 0) + 1
    depth_stats = {
        "sampled_frames": len(sampled),
        "invalid_values": depth_invalid,
        "valid_min_mm": depth_min,
        "valid_max_mm": depth_max,
    }
    confidence_stats = {
        "sampled_frames": len(sampled) if src.confidence else 0,
        "level_counts": confidence_counts,
    }
    return depth_grid, confidence_grid, depth_stats, confidence_stats, depth_assets, conf_assets


def _frame_records(src: StrayLidarSource, rgb: dict, depth_grid):
    calibrations, poses, observations = [], [], []
    for row in src.odometry:
        native = integer(row["frame"])
        calibrations.append(
            {
                "id": f"cal-{native:06d}",
                "native_frame_id": str(native),
                "K": [
                    [float(row["fx"]), 0.0, float(row["cx"])],
                    [0.0, float(row["fy"]), float(row["cy"])],
                    [0.0, 0.0, 1.0],
                ],
                "reference_grid": [rgb["width"], rgb["height"]],
                "source": "odometry.csv per-frame",
                "distortion_center_x": row.get("distortion_center_x") or None,
                "distortion_center_y": row.get("distortion_center_y") or None,
            }
        )
        poses.append(
            {
                "id": f"pose-{native:06d}",
                "native_frame_id": str(native),
                "world_from_camera": {
                    "t": [float(row["x"]), float(row["y"]), float(row["z"])],
                    "q": [
                        float(row["qw"]),
                        float(row["qx"]),
                        float(row["qy"]),
                        float(row["qz"]),
                    ],
                },
                "pose_direction": "T_world_camera (p_world = R * p_camera + t)",
                "quaternion_order": "qw,qx,qy,qz",
                "axes": "OpenCV/Rerun RDF: x right, y down, z forward",
                "translation_units": "metres (FORMAT_REFERENCE_ASSUMED)",
                "source": "odometry.csv",
                "convention_evidence": CONVENTION_EVIDENCE,
            }
        )
        depth_path = src.depth[native].relative_to(src.root).as_posix()
        observations.append(
            {
                "id": f"obs-{native:06d}",
                "asset_id": "",
                "room_id": "room-1",
                "source_path": depth_path,
                "native_frame_id": str(native),
                "pixel_grid": list(depth_grid),
                "camera_K_ref": f"cal-{native:06d}",
                "pose_ref": f"pose-{native:06d}",
                "rgb_asset_id": "asset-rgb",
                "rgb_decoded_rank": native - 1 if native >= 1 else None,
                "timestamp": {
                    "value": float(row["timestamp"]),
                    "timezone": None,
                    "source": "odometry.csv",
                    "domain": "sensor",
                },
                "processing_eligibility": "INGESTION_ONLY",
            }
        )
    return calibrations, poses, observations


def _capabilities(src: StrayLidarSource) -> dict:
    return {
        "rgb": CAPABILITY_VERIFIED_FORMAT,
        "lidar_depth": CAPABILITY_PRESENT_UNVERIFIED,
        "confidence": CAPABILITY_PRESENT_UNVERIFIED if src.confidence else CAPABILITY_ABSENT,
        "camera_intrinsics": CAPABILITY_PRESENT_UNVERIFIED,
        "calibration": CAPABILITY_PRESENT_UNVERIFIED,
        "poses": CAPABILITY_PRESENT_UNVERIFIED,
        "imu": CAPABILITY_PRESENT_UNVERIFIED,
        "timestamps": CAPABILITY_PRESENT_UNVERIFIED,
        "measured_depth": CAPABILITY_PRESENT_UNVERIFIED,
        "grounding_object": CAPABILITY_ABSENT,
        "exif": CAPABILITY_ABSENT,
    }


def _conventions(rgb: dict, depth_grid, confidence_grid) -> dict:
    scale = None
    if depth_grid and depth_grid[0] and depth_grid[1]:
        if rgb["width"] * depth_grid[1] == rgb["height"] * depth_grid[0]:
            scale = [
                round(rgb["width"] / depth_grid[0], 6),
                round(rgb["height"] / depth_grid[1], 6),
            ]
    return {
        "depth_units": "millimetres (FORMAT_REFERENCE_ASSUMED)",
        "depth_encoding": "uint16 grayscale PNG",
        "invalid_depth_value": 0,
        "depth_definition": "optical-axis depth (assumed, not verified)",
        "depth_grid": depth_grid,
        "confidence_encoding": "uint8 grayscale PNG (levels 0-2 assumed)"
        if confidence_grid
        else None,
        "confidence_grid": confidence_grid,
        "intrinsics_reference_grid": [rgb["width"], rgb["height"]],
        "rgb_to_depth_grid_scale": scale,
        "pose_direction": "T_world_camera (p_world = R * p_camera + t)",
        "quaternion_order": "qw,qx,qy,qz",
        "axes": "OpenCV/Rerun RDF: x right, y down, z forward",
        "translation_units": "metres (FORMAT_REFERENCE_ASSUMED)",
        "world_frame": "exporter-defined; not recentered",
        "second_axis_flip_applied": False,
        "evidence": CONVENTION_EVIDENCE,
    }


def _lidar_findings(src: StrayLidarSource, rgb: dict, sample_frames: int) -> list[dict]:
    findings = [
        {
            "code": "DEPTH_UNITS_UNVERIFIED",
            "details": {"assumed": "millimetres", "evidence": CONVENTION_EVIDENCE},
        },
        {
            "code": "CONVENTIONS_UNVERIFIED",
            "details": {"geometry_readiness": "CONVENTIONS_UNVERIFIED"},
        },
        {
            "code": "IMU_UNITS_UNRESOLVED",
            "details": {"note": "raw acceleration/gyro retained; units not converted"},
        },
    ]
    if not src.confidence:
        findings.append(
            {"code": "CONFIDENCE_ABSENT", "details": {"note": "no confidence maps supplied"}}
        )
    if rgb["frame_count"] and rgb["frame_count"] != len(src.odometry) - 1:
        findings.append(
            {
                "code": "RGB_FRAME_COUNT_DISCREPANCY",
                "details": {
                    "rgb_decoded_frames": rgb["frame_count"],
                    "camera_records": len(src.odometry),
                },
            }
        )
    return findings


def _source_identity(assets: list[dict]) -> str:
    payload = sorted(
        (
            {
                "source_path": asset["source_paths"][0],
                "sha256": asset["sha256"],
                "bytes": asset["bytes"],
            }
            for asset in assets
        ),
        key=lambda item: item["source_path"],
    )
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _assert_sources_unchanged(assets: list[dict], source: Path) -> None:
    for asset in assets:
        relative = asset["source_paths"][0]
        require(
            sha256(source / relative) == asset["sha256"],
            "SOURCE_CHANGED",
            f"Source changed during ingestion: {relative}",
        )
