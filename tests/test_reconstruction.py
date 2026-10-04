"""Projection/gauge/degeneracy and source/transaction boundaries for sparse reconstruction."""

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

try:
    import numpy as np
    import pycolmap as pc
except ImportError as error:
    raise unittest.SkipTest("Install the reconstruct extra") from error

from fixtures import FakeVideoInspector, fixture, media, pose_row
from test_preprocessing import SyntheticDecoder

from cozmo_ingestion import IngestionPipeline, IngestionRequest
from cozmo_ingestion.adapters.sensor_recorder import POSE_HEADER
from cozmo_ingestion.errors import IngestionError
from cozmo_ingestion.storage import sha256, write_csv
from cozmo_preprocessing import PreprocessingPipeline, PreprocessingRequest
from cozmo_reconstruction import ReconstructionPipeline, ReconstructionPolicy, ReconstructionRequest
from cozmo_reconstruction.analysis import point_metrics
from cozmo_reconstruction.cameras import convert_camera, project, select_pairs
from cozmo_reconstruction.colmap import assert_fixed, camera_records, triangulation_options
from cozmo_reconstruction.inputs import PreparedInput
from cozmo_reconstruction.verification import verify_reconstruction


def camera(center=(0, 0, 0), shift=0):
    c2w = np.eye(4)
    c2w[:3, 3] = center
    k = {"K": [[500, 0, 320], [0, 510, 240], [0, 0, 1]], "image_size": [640, 480]}
    pose = {"world_from_camera": c2w.tolist()}
    return k, pose, convert_camera(k, pose, shift)


def prepared(root):
    fixture(root / "raw")
    rows = [pose_row(i, i, f"1000000000.{i * 250000:06d}") for i in range(3)]
    write_csv(root / "raw/arkit_pose.csv", POSE_HEADER, rows)
    fake = media()
    fake["frames"] = [
        {"best_effort_timestamp": i * 250000, "width": 100, "height": 60} for i in range(3)
    ]
    IngestionPipeline(video_inspector=FakeVideoInspector(lambda _: fake)).run(
        IngestionRequest(root / "raw", root / "bundle")
    )
    PreprocessingPipeline(decoder=SyntheticDecoder()).run(
        PreprocessingRequest(root / "bundle", root / "prepared", root / "raw")
    )
    return ReconstructionRequest(root / "prepared", root / "bundle", root / "result", root / "raw")


class ReconstructionTests(unittest.TestCase):
    def test_zero_parallax_run_stays_weak_and_export_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            request = prepared(Path(tmp))
            result = ReconstructionPipeline().run(request)
            self.assertEqual(result["report"]["accepted_points"], 0)
            self.assertEqual(result["report"]["geometry_signal"], "WEAK")
            self.assertEqual(result["verification"]["status"], "PASSED")
            hashes_before = {
                p.relative_to(request.output).as_posix(): sha256(p)
                for p in request.output.rglob("*")
                if p.is_file()
            }
            for _ in range(2):
                self.assertEqual(
                    verify_reconstruction(
                        request.output, request.prepared, request.bundle, request.source_root
                    )["status"],
                    "PASSED",
                )
            self.assertEqual(
                hashes_before,
                {
                    p.relative_to(request.output).as_posix(): sha256(p)
                    for p in request.output.rglob("*")
                    if p.is_file()
                },
            )
            with self.assertRaises(IngestionError):
                ReconstructionPipeline().run(request)
            (request.output / "cloud.ply").write_bytes(b"modified")
            with self.assertRaises(IngestionError):
                verify_reconstruction(
                    request.output, request.prepared, request.bundle, request.source_root
                )

    def test_optical_projection_inverse_and_pixel_hypothesis(self):
        _, pose, converted = camera((1, 2, 3), 0.5)
        xy, z = project(converted, [1, 2, 5])
        np.testing.assert_allclose(xy, [320.5, 240.5])
        self.assertEqual(z, 2)
        np.testing.assert_allclose(
            np.asarray(converted["camera_from_world"]) @ pose["world_from_camera"], np.eye(4)
        )
        rotation = np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]])
        pose["world_from_camera"] = np.block(
            [[rotation, np.zeros((3, 1))], [np.zeros((1, 3)), np.ones((1, 1))]]
        ).tolist()
        k, _, _ = camera()
        xy, z = project(convert_camera(k, pose, 0), [2, 0, 0])
        np.testing.assert_allclose(xy, [320, 240])
        self.assertEqual(z, 2)

    def test_rejects_nonrigid_and_invalid_calibration(self):
        k, pose, _ = camera()
        pose["world_from_camera"][0][0] = 2
        with self.assertRaises(IngestionError):
            convert_camera(k, pose, 0)
        k["K"][0][0] = -1
        _, pose, _ = camera()
        with self.assertRaises(IngestionError):
            convert_camera(k, pose, 0)

    def test_tracks_reject_pure_rotation_behind_camera_and_conflict(self):
        policy = ReconstructionPolicy()
        cams = {i: camera()[2] for i in range(3)}
        point = {
            "xyz_m": [0, 0, 4],
            "observations": [{"rank": i, "xy": [320, 240]} for i in range(3)],
        }
        self.assertIn("LOW_PARALLAX", point_metrics(point, cams, policy)["reasons"])
        cams = {i: camera((i * 0.2, 0, 0))[2] for i in range(3)}
        point["observations"] = [
            {"rank": i, "xy": project(cams[i], point["xyz_m"])[0].tolist()} for i in range(3)
        ]
        self.assertTrue(point_metrics(point, cams, policy)["accepted"])
        point["observations"][1]["xy"][0] += 20
        self.assertIn("REPROJECTION", point_metrics(point, cams, policy)["reasons"])
        point["xyz_m"][2] = -4
        self.assertIn("NONPOSITIVE_DEPTH", point_metrics(point, cams, policy)["reasons"])
        point["observations"][1]["rank"] = 0
        self.assertIn("DUPLICATE_IMAGE_IN_TRACK", point_metrics(point, cams, policy)["reasons"])

    def test_input_selection_tamper_and_reference_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            request = prepared(Path(tmp))
            data = PreparedInput(request, ReconstructionPolicy())
            self.assertEqual(len(data.mapping), 3)
            self.assertFalse(any("reference" in key for v in data.mapping for key in v))
            for ranks in ((0, 0, 2), (0, 1, 99), (0, 1), (2, 1, 0)):
                with self.assertRaises(IngestionError):
                    PreparedInput(replace(request, ranks=ranks), ReconstructionPolicy())
            (request.prepared / "images/000000.jpg").write_bytes(b"modified")
            with self.assertRaises(IngestionError):
                PreparedInput(request, ReconstructionPolicy())

    def test_backend_failure_never_publishes_or_edits_inputs(self):
        class FailingBackend:
            def run(self, stage, policy):
                raise IngestionError("SIMULATED_FAILURE", "Backend failure")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = prepared(root)
            before = sha256(root / "raw/arkit_pose.csv")
            with self.assertRaises(IngestionError):
                ReconstructionPipeline(backend=FailingBackend()).run(request)
            self.assertFalse(request.output.exists())
            self.assertEqual(before, sha256(root / "raw/arkit_pose.csv"))
            failure = list(root.glob("result.ingest-*/manifest.json"))[0]
            self.assertEqual(json.loads(failure.read_text())["status"], "FAILED")

    def test_pairing_includes_temporal_links_and_distant_revisit(self):
        mapping = []
        for i in range(30):
            k, pose, _ = camera((0 if i in (0, 29) else 3, 0, 0))
            mapping.append(
                {
                    "rank": i,
                    "image": str(i),
                    "relative_seconds": str(i),
                    "calibration": k,
                    "pose": pose,
                }
            )
        pairs = select_pairs(mapping, ReconstructionPolicy())
        self.assertIn(("0", "1"), pairs)
        self.assertIn(("0", "29"), pairs)
        self.assertEqual(len(select_pairs(mapping[:24], ReconstructionPolicy())), 276)

    def test_policy_bounds_and_fixed_camera_audit(self):
        for config in (
            {"threads": 0},
            {"min_track_length": 2},
            {"principal_point_shift": 1},
            {"max_views": 301},
            {"min_angle_degrees": float("nan")},
        ):
            with self.assertRaises(ValueError):
                ReconstructionPolicy(**config)
        base = {
            "rank": 0,
            "image_id": 1,
            "camera_id": 1,
            "image": "0.jpg",
            "model": "PINHOLE",
            "image_size": [640, 480],
            "params": [500, 510, 320, 240],
            "camera_from_world": np.eye(4).tolist(),
            "center_m": [0, 0, 0],
        }
        moved = json.loads(json.dumps(base))
        moved["camera_from_world"][0][3] = 0.001
        with self.assertRaises(IngestionError):
            assert_fixed([base], [moved])

    def test_real_triangulator_recovers_known_geometry_without_camera_changes(self):
        rng = np.random.default_rng(7)
        xyz = rng.uniform([-0.5, -0.5, 3], [0.5, 0.5, 5], size=(50, 3))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "images").mkdir()
            model = pc.Reconstruction()
            by_name = {}
            with pc.Database.open(root / "database.db") as db:
                for i in range(1, 4):
                    k, pose, converted = camera(((i - 1) * 0.3, 0, 0), 0.5)
                    cam = pc.Camera(
                        camera_id=i,
                        model="PINHOLE",
                        width=640,
                        height=480,
                        params=converted["params"],
                    )
                    model.add_camera_with_trivial_rig(cam)
                    xy = np.array([project(converted, point)[0] for point in xyz])
                    image = pc.Image(name=f"{i}.jpg", image_id=i, camera_id=i, keypoints=xy)
                    model.add_image_with_trivial_frame(
                        image, pc.Rigid3d(np.array(converted["camera_from_world"])[:3])
                    )
                    db.write_camera(cam, use_camera_id=True)
                    db.write_rig(model.rig(i), use_rig_id=True)
                    db.write_frame(model.frame(i), use_frame_id=True)
                    db.write_image(model.image(i), use_image_id=True)
                    db.write_keypoints(i, xy.astype(np.float32))
                    by_name[image.name] = {"rank": i, "calibration": k, "pose": pose}
                for a, b in ((1, 2), (1, 3), (2, 3)):
                    g = pc.TwoViewGeometry()
                    g.config = pc.TwoViewGeometryConfiguration.CALIBRATED
                    g.inlier_matches = np.array([[i, i] for i in range(50)], dtype=np.uint32)
                    db.write_two_view_geometry(a, b, g)
            before = camera_records(model, by_name)
            opts = triangulation_options(ReconstructionPolicy(), model)
            opts.extract_colors = False
            result = pc.triangulate_points(
                model,
                root / "database.db",
                root / "images",
                root / "model",
                options=opts,
                refine_intrinsics=False,
            )
            assert_fixed(before, camera_records(result, by_name))
            self.assertEqual(result.num_points3D(), 50)
            recovered = np.array([p.xyz for p in result.points3D.values()])
            self.assertLess(
                np.max(np.min(np.linalg.norm(recovered[:, None] - xyz, axis=2), axis=1)), 1e-5
            )


if __name__ == "__main__":
    unittest.main()
