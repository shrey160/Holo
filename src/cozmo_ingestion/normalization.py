"""Build canonical observations while preserving native data and quality findings."""

import math

from .clocks import timing
from .contracts import DEFAULT_POLICY, IngestionPolicy
from .errors import require
from .models import (
    CameraObservations,
    CanonicalObservations,
    SensorObservations,
    SourceCapture,
    VideoInspection,
)
from .numeric import integer, number, quaternion_pose


def normalize_camera(
    capture: SourceCapture,
    video: VideoInspection,
    ticks: list[int],
    capture_id: str,
    annotated: dict,
    policy: IngestionPolicy,
) -> CameraObservations:
    """Validate native camera records and retain every frame/K/pose association."""
    rows, origin = capture.camera_rows, capture.origin
    findings = []
    frame_rows, calibrations, poses = [], [], []
    slots, limited, high_speed = [], [], []
    width, height = video.stream["width"], video.stream["height"]
    for i, row in enumerate(rows):
        require(
            integer(row["width_px"]) == width
            and integer(row["height_px"]) == height
            and video.frames[i].get("width", width) == width
            and video.frames[i].get("height", height) == height,
            "CALIBRATION_GRID_MISMATCH",
            str(i),
        )
        fx, fy, cx, cy = [float(number(row[k])) for k in ["fx_px", "fy_px", "cx_px", "cy_px"]]
        require(
            fx > 0 and fy > 0 and 0 <= cx < width and 0 <= cy < height, "INVALID_INTRINSICS", str(i)
        )
        require(number(row["exposure_sec"]) > 0, "INVALID_EXPOSURE", str(i))
        transform, norm = quaternion_pose(row, policy)
        frame_id = f"{capture_id}:{i:06d}"
        rel = number(row["sensor_sec"]) - origin
        require(bool(row["tracking_state"]), "MISSING_TRACKING_STATE", str(i))
        if row["tracking_state"] != "normal":
            limited.append(i)
        if i and integer(row["record_slot"]) > integer(rows[i - 1]["record_slot"]) + 1:
            slots.append(
                {
                    "before_frame": i - 1,
                    "after_frame": i,
                    "skipped_slots": integer(row["record_slot"])
                    - integer(rows[i - 1]["record_slot"])
                    - 1,
                    "camera_interval_seconds": str(
                        number(row["sensor_sec"]) - number(rows[i - 1]["sensor_sec"])
                    ),
                }
            )
        if i:
            step = math.sqrt(
                sum((float(row[k]) - float(rows[i - 1][k])) ** 2 for k in ["tx_m", "ty_m", "tz_m"])
            )
            speed = step / float(number(row["sensor_sec"]) - number(rows[i - 1]["sensor_sec"]))
            if speed > policy.apparent_pose_speed_warning_m_s:
                high_speed.append(
                    {
                        "before_frame": i - 1,
                        "after_frame": i,
                        "apparent_speed_m_s": speed,
                        "step_m": step,
                    }
                )
        candidates = [
            obj["id"]
            for obj in annotated["reference_objects"]
            if i in obj["candidate_source_frame_indices"]
        ]
        frame_rows.append(
            {
                "frame_id": frame_id,
                "camera_id": "wide",
                "video_asset_id": "wide.mp4",
                "source_frame_index": i,
                "decoded_rank": i,
                "record_slot": row["record_slot"],
                "source_line": row["_source_line"],
                "media_pts_ticks": ticks[i],
                "media_timebase": video.stream["time_base"],
                "sensor_seconds": row["sensor_sec"],
                "utc_seconds": row["utc_sec"],
                "relative_seconds": str(rel),
                "calibration_id": frame_id,
                "pose_id": frame_id,
                "tracking_state": row["tracking_state"],
                "pose_tracking_normal": row["tracking_state"] == "normal",
                "exposure_seconds": row["exposure_sec"],
                "scale_prior_candidate_ids": ";".join(candidates),
                "decoded_status": "VALIDATED",
            }
        )
        calibrations.append(
            {
                "id": frame_id,
                "source_frame_index": i,
                "camera_id": "wide",
                "K": [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]],
                "image_size": [width, height],
                "pixel_transform": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                "pixel_coordinates": "top-left; x right, y down",
                "distortion": None,
                "distortion_status": "UNVERIFIED",
                "source": "arkit_pose.csv",
                "evidence": "EXPORTER_DECLARED",
            }
        )
        poses.append(
            {
                "id": frame_id,
                "source_frame_index": i,
                "relative_seconds": str(rel),
                "world_from_camera": transform,
                "matrix_order": "row-major arrays; column-vector application",
                "source_quaternion_wxyz": [row[k] for k in ["qw", "qx", "qy", "qz"]],
                "source_translation_m": [row[k] for k in ["tx_m", "ty_m", "tz_m"]],
                "quaternion_norm": norm,
                "quaternion_normalization": "normalize serialization rounding for matrix construction; source retained",
                "tracking_state": row["tracking_state"],
                "segment_id": "source-session-unverified-continuity",
                "units": "m",
                "camera_axes": "optical x right, y down, z forward",
                "source": "supplied ARKit VIO; unrefined",
                "physically_validated": False,
            }
        )

    def finding(code, details):
        findings.append({"code": code, "severity": "WARNING", "details": details})

    if slots:
        finding(
            "RECORD_SLOT_DISCONTINUITY",
            {
                "events": slots,
                "interpretation": "slot indices alone do not establish dropped images",
            },
        )
    if limited:
        finding(
            "NON_NORMAL_TRACKING", {"source_frame_indices": limited, "observations_retained": True}
        )
    if high_speed:
        finding(
            "APPARENT_POSE_SPEED",
            {
                "events": high_speed,
                "threshold_m_s": policy.apparent_pose_speed_warning_m_s,
                "diagnosis": "UNVERIFIED",
            },
        )
    return CameraObservations(frame_rows, calibrations, poses, limited, findings)


def normalize_sensors(
    capture: SourceCapture, stream_headers: dict[str, list[str]]
) -> SensorObservations:
    """Keep original sensor values/times and report missing boundary coverage."""
    rows, tables, origin = capture.camera_rows, capture.sensor_rows, capture.origin
    findings, sensors = [], {}

    def finding(code, details):
        findings.append({"code": code, "severity": "WARNING", "details": details})

    stream_statistics = {"camera": timing(rows, origin)}
    for key, samples in tables.items():
        stream_statistics[key] = timing(samples, origin)
        if key in ["accelerometer", "gyroscope"]:
            require(
                number(samples[0]["sensor_sec"]) <= number(rows[-1]["sensor_sec"])
                and number(samples[-1]["sensor_sec"]) >= origin,
                "NO_IMU_CAMERA_OVERLAP",
                key,
            )
            if number(samples[0]["sensor_sec"]) > origin or number(
                samples[-1]["sensor_sec"]
            ) < number(rows[-1]["sensor_sec"]):
                finding(
                    "PARTIAL_IMU_BOUNDARY_COVERAGE",
                    {"stream": key, **stream_statistics[key], "extrapolation": "NONE"},
                )
        output_rows = [
            {
                "source_row": i,
                "source_line": row["_source_line"],
                "relative_seconds": str(number(row["sensor_sec"]) - origin),
                **{k: row[k] for k in stream_headers[key]},
            }
            for i, row in enumerate(samples)
        ]
        sensors[key] = output_rows
    return SensorObservations(sensors, stream_statistics, findings)


def capture_findings(capture: SourceCapture, annotated: dict) -> list[dict]:
    """Describe capture-level limitations without changing measurements."""
    rows, meta = capture.camera_rows, capture.metadata
    findings = []

    def finding(code, details):
        findings.append({"code": code, "severity": "WARNING", "details": details})

    setting_cap = number(meta["recording_settings"]["arkit_camera"]["max_exposure_duration_sec"])
    overs = [i for i, r in enumerate(rows) if number(r["exposure_sec"]) > setting_cap]
    if overs:
        finding(
            "EXPOSURE_EXCEEDS_REQUESTED_CAP",
            {
                "source_frame_indices": overs,
                "requested_cap_seconds": str(setting_cap),
                "observations_retained": True,
            },
        )
    if annotated["reference_objects"]:
        finding(
            "SCALE_PRIOR_NOT_LOCALIZED",
            {"dimensions_source": "USER_REPORTED", "scale_applied": False},
        )
    finding(
        "PHYSICAL_CALIBRATION_UNVERIFIED",
        {
            "RGB_IMU_synchronization": "UNVERIFIED",
            "camera_IMU_extrinsics": "UNVERIFIED",
            "metric_accuracy": "UNVERIFIED",
        },
    )
    return findings


def normalize(
    capture: SourceCapture,
    video: VideoInspection,
    ticks: list[int],
    capture_id: str,
    annotated: dict,
    stream_headers: dict[str, list[str]],
    policy: IngestionPolicy = DEFAULT_POLICY,
) -> CanonicalObservations:
    """Compose independent camera/sensor normalization into a validated bundle input."""
    camera = normalize_camera(capture, video, ticks, capture_id, annotated, policy)
    sensors = normalize_sensors(capture, stream_headers)
    return CanonicalObservations(
        camera.frames,
        camera.calibration,
        camera.poses,
        sensors.rows,
        sensors.statistics,
        camera.limited_frames,
        camera.findings + sensors.findings + capture_findings(capture, annotated),
    )
