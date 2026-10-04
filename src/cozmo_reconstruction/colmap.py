"""Pinned PyCOLMAP adapter; all poses, intrinsics and rig transforms remain constant."""

import json
import time
from pathlib import Path

import numpy as np
import pycolmap as pc

from cozmo_ingestion.errors import require
from cozmo_ingestion.storage import write_json, write_lines

from .analysis import point_metrics
from .cameras import convert_camera


def serializable(value):
    if isinstance(value, dict):
        return {str(k): serializable(v) for k, v in value.items()}
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, (list, tuple)):
        return [serializable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def triangulation_options(policy, model):
    opts = pc.IncrementalPipelineOptions()
    opts.num_threads = policy.threads
    opts.random_seed = policy.seed
    opts.fix_existing_frames = True
    opts.mapper.fix_existing_frames = True
    opts.constant_cameras = set(model.cameras)
    opts.constant_rigs = set(model.rigs)
    opts.mapper.constant_cameras = set(model.cameras)
    opts.mapper.constant_rigs = set(model.rigs)
    opts.ba_refine_focal_length = False
    opts.ba_refine_principal_point = False
    opts.ba_refine_extra_params = False
    opts.ba_refine_sensor_from_rig = False
    opts.mapper.abs_pose_refine_focal_length = False
    opts.mapper.abs_pose_refine_extra_params = False
    opts.mapper.filter_max_reproj_error = policy.max_reprojection_pixels
    opts.mapper.filter_min_tri_angle = policy.min_angle_degrees
    opts.triangulation.min_angle = policy.min_angle_degrees
    opts.triangulation.random_seed = policy.seed
    opts.triangulation.ignore_two_view_tracks = True
    opts.triangulation.merge_max_reproj_error = policy.max_reprojection_pixels
    opts.triangulation.complete_max_reproj_error = policy.max_reprojection_pixels
    return opts


def camera_records(model, by_name):
    records = []
    for image_id, img in sorted(model.images.items()):
        source = by_name[img.name]
        camera = model.camera(img.camera_id)
        matrix = np.eye(4)
        matrix[:3] = img.cam_from_world().matrix()
        records.append(
            {
                "rank": source["rank"],
                "image_id": image_id,
                "camera_id": img.camera_id,
                "image": img.name,
                "model": camera.model_name,
                "image_size": [camera.width, camera.height],
                "params": camera.params.tolist(),
                "camera_from_world": matrix.tolist(),
                "center_m": img.projection_center().tolist(),
            }
        )
    return records


def assert_fixed(before, after):
    require(len(before) == len(after), "RECONSTRUCTION_CAMERAS_CHANGED", "Camera count")
    for a, b in zip(before, after, strict=True):
        require(
            all(
                a[k] == b[k]
                for k in ("rank", "image_id", "camera_id", "image", "model", "image_size")
            )
            and all(
                np.allclose(a[k], b[k], atol=1e-10, rtol=0)
                for k in ("params", "camera_from_world", "center_m")
            ),
            "RECONSTRUCTION_CAMERAS_CHANGED",
            str(a["rank"]),
        )


def export_points(model, by_name):
    records = []
    for point_id, point in sorted(model.points3D.items()):
        observations = []
        for element in point.track.elements:
            img = model.image(element.image_id)
            observations.append(
                {
                    "rank": by_name[img.name]["rank"],
                    "image_id": element.image_id,
                    "keypoint_index": element.point2D_idx,
                    "xy": img.point2D(element.point2D_idx).xy.tolist(),
                }
            )
        records.append(
            {
                "point_id": point_id,
                "xyz_m": point.xyz.tolist(),
                "rgb": point.color.tolist(),
                "observations": observations,
            }
        )
    return records


def run_colmap(stage: Path, policy):
    require(pc.__version__ == "4.2.1", "RECONSTRUCTION_BACKEND_VERSION", pc.__version__)
    started = time.perf_counter()
    mapping = json.loads((stage / "input_mapping.json").read_text(encoding="utf-8"))
    by_name = {v["image"]: v for v in mapping}
    database = stage / "database.db"
    images = stage / "images"
    extract = pc.FeatureExtractionOptions()
    extract.num_threads = policy.threads
    extract.use_gpu = False
    extract.max_image_size = max(max(v["calibration"]["image_size"]) for v in mapping)
    extract.sift.max_num_features = policy.max_features
    reader = pc.ImageReaderOptions(camera_model="PINHOLE")
    print("Extract native-grid CPU SIFT", flush=True)
    pc.extract_features(
        database,
        images,
        image_names=list(by_name),
        camera_mode=pc.CameraMode.PER_IMAGE,
        reader_options=reader,
        extraction_options=extract,
        device=pc.Device.cpu,
    )
    extraction_seconds = time.perf_counter() - started
    model = pc.Reconstruction()
    with pc.Database.open(database) as db:
        db_images = db.read_all_images()
        require(len(db_images) == len(mapping), "RECONSTRUCTION_IMAGE_IDENTITY", "Extraction count")
        for img in db_images:
            converted = convert_camera(
                by_name[img.name]["calibration"],
                by_name[img.name]["pose"],
                policy.principal_point_shift,
            )
            camera = db.read_camera(img.camera_id)
            camera.params = converted["params"]
            camera.has_prior_focal_length = True
            db.update_camera(camera)
            model.add_camera_with_trivial_rig(camera)
            feature_image = pc.Image(
                name=img.name,
                camera_id=img.camera_id,
                image_id=img.image_id,
                keypoints=db.read_keypoints(img.image_id)[:, :2],
            )
            transform = pc.Rigid3d(np.asarray(converted["camera_from_world"])[:3])
            model.add_image_with_trivial_frame(feature_image, transform)
    before = camera_records(model, by_name)
    write_json(stage / "cameras_before.json", before)
    (stage / "initial_model").mkdir()
    model.write(stage / "initial_model")
    matching = pc.FeatureMatchingOptions()
    matching.num_threads = policy.threads
    matching.use_gpu = False
    matching.max_num_matches = policy.max_features
    verification = pc.TwoViewGeometryOptions(min_num_inliers=20)
    verification.ransac.random_seed = policy.seed
    verification.ransac.max_error = policy.max_reprojection_pixels
    pairing = pc.ImportedPairingOptions()
    pairing.match_list_path = stage / "pairs.txt"
    print("Match temporal and revisit pairs", flush=True)
    tick = time.perf_counter()
    pc.match_image_pairs(
        database,
        matching_options=matching,
        pairing_options=pairing,
        verification_options=verification,
        device=pc.Device.cpu,
    )
    matching_seconds = time.perf_counter() - tick
    options = triangulation_options(policy, model)
    print("Triangulate with all cameras fixed", flush=True)
    tick = time.perf_counter()
    result = pc.triangulate_points(
        model, database, images, stage / "model", options=options, refine_intrinsics=False
    )
    after = camera_records(result, by_name)
    assert_fixed(before, after)
    # Preserve every backend candidate and explicitly partition valid geometry.
    candidates = export_points(result, by_name)
    write_lines(stage / "candidate_points.jsonl", candidates)
    converted_cameras = {}
    for c in after:
        converted = convert_camera(
            by_name[c["image"]]["calibration"],
            by_name[c["image"]]["pose"],
            policy.principal_point_shift,
        )
        converted_cameras[c["rank"]] = converted
    rejected = 0
    for point in candidates:
        if not point_metrics(point, converted_cameras, policy)["accepted"]:
            result.delete_point3D(point["point_id"])
            rejected += 1
    result.update_point_3d_errors()
    result.write(stage / "model")
    result.write_text(stage / "model")
    result.export_PLY(stage / "cloud.ply")
    write_json(stage / "cameras.json", after)
    write_lines(stage / "points.jsonl", export_points(result, by_name))
    with pc.Database.open(database) as db:
        pair_ids, geometries = db.read_two_view_geometries()
        write_json(
            stage / "pair_geometry.json",
            [
                {
                    "image_ids": list(pc.pair_id_to_image_pair(pair_id)),
                    "config": str(g.config),
                    "inliers": len(g.inlier_matches),
                }
                for pair_id, g in zip(pair_ids, geometries, strict=True)
            ],
        )
        feature_count = int(db.num_keypoints())
    write_json(
        stage / "backend.json",
        {
            "backend": "pycolmap",
            "version": pc.__version__,
            "cuda_available": pc.has_cuda,
            "device": "CPU",
            "feature_count": feature_count,
            "rejected_candidate_tracks": rejected,
            "options": {
                "extraction": serializable(extract.todict()),
                "matching": serializable(matching.todict()),
                "verification": serializable(verification.todict()),
                "triangulation": serializable(options.todict()),
                "refine_intrinsics": False,
            },
            "timings_seconds": {
                "extraction": extraction_seconds,
                "matching": matching_seconds,
                "triangulation_and_export": time.perf_counter() - tick,
                "total": time.perf_counter() - started,
            },
        },
    )
    print(f"Finished: {result.num_points3D()} sparse points", flush=True)
