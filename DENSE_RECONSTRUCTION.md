# Fixed-pose RGB stereo depth

Subsequent stage: [surface hypotheses and RGB evidence](SURFACES.md) now executes on this verified dense result. It leaves this bundle unchanged; architectural identity, dimensions and floorplan remain unconfirmed.

Dense reconstruction follows the independently verified sparse stage. It estimates optical-camera Z depth from overlapping RGB views with COLMAP CUDA PatchMatch, retains the source poses, then independently checks every candidate pixel against neighboring depth maps. This is an experimental reconstruction result, not a dimensionally validated floorplan.

The geometry inputs are selected RGB, per-frame intrinsics and source ARKit optical camera-to-world poses. Captured depth/confidence, grounding dimensions/photo, evaluation geometry and new IMU integration are excluded. Independent IMU remains available in preprocessing diagnostics. The source world and estimated metre scale are preserved; physical accuracy remains **UNVERIFIED**.

## Runtime and commands

`pycolmap-cuda12==4.2.1` and its CUDA 12 dependencies are pinned in `uv.lock`. The `dense` and `reconstruct` extras conflict intentionally because both COLMAP distributions provide the same Python module. Use separate environments or Docker targets. Current Windows CPU PyCOLMAP supports independent result verification; its wheel cannot run CUDA PatchMatch. Native Linux with a compatible NVIDIA driver can use `uv sync --locked --extra dense` and `uv run --locked --extra dense cozmo-dense ...`. No Docker is required for existing native ingestion, preprocessing or sparse reconstruction.

Build the separate worker from this folder:

```shell
docker build --target dense -t holo-dense:0.2.0 .
docker run --rm --gpus all --entrypoint python holo-dense:0.2.0 -c "import pycolmap as p; print(p.__version__, p.has_cuda)"
```

For the local dataset, create a new output under `outputs/linux-reconstruction`; mount the workspace read-only and only the results folder writable:

```shell
docker run --rm --gpus all --mount "type=bind,source=C:/Shrey_Projs/Recruitements_comp/tkh_cozmo,target=/workspace,readonly" --mount "type=bind,source=C:/Shrey_Projs/Recruitements_comp/tkh_cozmo/proto-2/outputs/linux-reconstruction,target=/results" holo-dense:0.2.0 /workspace/proto-2/outputs/single-room-sparse-100-v2 /workspace/proto-2/outputs/single-room-preprocessing-final /workspace/proto-2/outputs/single-room-cli-v2 /results/my-dense-run --source /workspace/test_data/iphn-17/single_room --ranks-file /workspace/proto-2/outputs/dense-smoke-ranks.json
```

The optional JSON ranks file contains ascending unique `ranks` and optionally `sparse_manifest_sha256`; a mismatched binding is rejected. Omitting it admits all verified sparse views, up to 100. Controls: `--max-image-size` (960 default), `--neighbors` (6), `--iterations` (3), `--timeout` (1800 seconds). Existing outputs and source overlap are rejected. Worker failures preserve staging diagnostics and do not publish a final result.

Verify the resulting Linux artifacts on Windows, using the current CPU environment:

```shell
uv run --locked --extra reconstruct cozmo-dense outputs/single-room-sparse-100-v2 outputs/single-room-preprocessing-final outputs/single-room-cli-v2 outputs/linux-reconstruction/my-dense-run --source ../test_data/iphn-17/single_room --verify-only
```

Holo currently exposes ingestion/preprocessing. Sparse and dense stages are CLI workflows.

## System design

The [dense module README](src/cozmo_reconstruction/dense/README.md) describes ownership. `DensePipeline` audits the complete source chain, admits a bounded rank selection, builds a deterministic co-visibility schedule from accepted sparse tracks, invokes an injected worker with a timeout and publishes atomically after independent verification.

The isolated worker uses the verified model as a read-only input. COLMAP creates a derived image grid and PINHOLE camera calibration without pose refinement. At 960 pixels, native 1920×1080 images become 960×540; fx/cx scale by the width ratio and fy/cy by the height ratio. The adapter verifies the actual derived model against that transform. Coordinates follow COLMAP's corner-origin convention, with pixel centers at `(x+0.5,y+0.5)`. The original source pixel-center/distortion hypothesis remains physically unverified; no extra axis flip or scale fitting is applied.

PatchMatch estimates photometric depth then checks geometric consistency. The independent acceptance pass additionally requires valid finite Z in 0.1–20 source estimated metres, relative depth agreement ≤2%, a round-trip reprojection error ≤1 derived pixel and a ray angle ≥1 degree in at least two distinct neighboring views. Invalid/out-of-view/occluded/disagreeing samples fail that neighbor's check. Thresholds are engineering choices, not calibrated uncertainty intervals.

Accepted pixels are backprojected using their exact derived camera and fixed source pose. Every second pixel on each axis is exported before 1 cm voxel averaging. The point cloud contains observations only; holes are preserved. Pixel coverage is measured over selected images and must not be interpreted as percentage of room surface or property completeness. Sparse-depth agreement uses the same poses and RGB, so it is diagnostic rather than independent truth. No TSDF, closed mesh, floorplane, walls or room polygon is inferred in this milestone.

## Output contract and verification

- `manifest.json`: input exclusions, sparse manifest identity, immutable policy, module fingerprint and hashes of all derived artifacts.
- `input_mapping.json`, `neighbors.json`, `policy.json`: exact selected source associations and stereo schedule.
- `workspace/images`, `workspace/sparse`, `workspace/stereo`: derived RGB/calibration and COLMAP photometric/geometric depth and normal maps.
- `cameras.json`: source/derived grids, K parameters, fixed world-to-camera transforms and source-world centers.
- `masks/*.npz`: independently accepted pixels and number of supporting neighbors.
- `cloud.npz`, `cloud.ply`: source-world point cloud with RGB and no forced closure.
- `previews/*.jpg`: RGB, accepted depth (fixed 0–6 m color range; black means absent) and RGB with rejected regions dimmed.
- `report.json`, `preview.svg`, `backend.json`, `backend.log`: coverage/rejection/sparse agreement, orthogonal source-axis preview and runtime evidence.

Verification hashes every artifact, reaudits raw/ingested/preprocessed/sparse evidence, checks selected associations, co-visibility, actual derived model cameras, recomputes masks/cloud/report, and repeats the artifact audit. Integer/categorical decisions and hashes remain exact. Floating report summaries allow only `1e-10` absolute / `1e-12` relative roundoff; this addresses a measured cross-platform angle quantile difference of about `1.8e-15` degrees. It does not relax geometric acceptance thresholds. Published databases are inspected with read-only SQLite, never PyCOLMAP's writing database initializer.

## Trial status

Both background trials completed and were inspected after session resumption on 2026-10-04. The current engineering baseline is fixed-pose COLMAP RGB stereo; the learned comparison is retained separately and is not promoted into default fusion.

| Trial | Accepted image pixels | Voxel points | Backend time | Result |
|---|---:|---:|---:|---|
| 18 overlapping stereo views | 4,397,551 / 47.1274% | 393,754 | 112.47 s | GPU publication and Windows CPU verification pass |
| 100 stereo views | 12,606,053 / 24.3172% | 878,459 | 612.32 s | GPU publication and Windows CPU verification pass |
| 6 pose-conditioned learned views | 100,397 / 10.9873% | 22,833 | 74.35 s CPU inference | Separately verified experiment; weak consistent coverage |

Stereo targets: `outputs/linux-reconstruction/single-room-dense-18-v1` and `single-room-dense-100-v1`. The full run has 17,713,340 backend-valid pixels, 3,151,590 sampled accepted observations and 719 hashed artifacts. Repeated independent audits of both published stereo outputs preserved every byte. Camera grids/poses, source lineage, masks/clouds and reports were recomputed; final Linux verification also passed with the workspace mounted read-only. The 69-case Windows/Linux regression suite and Ruff checks pass. The wheel installed/imported in a fresh CPU venv, native/container CLI checks passed, and packaging excludes private/generated content. No original capture, prepared view or sparse database was modified. Holo remains healthy and the CLI reconstruction stages have no HTTP integration yet.

Lower percentage in the 100-view run reflects the additional viewpoints and weak/low-parallax regions, not a like-for-like regression of the smoke selection. Six opening views retain no independently accepted pixels; other weak views have small support. Source/world orthogonal cloud preview and individual floor/bed/window/room-surface images were inspected. Bed, furniture, textured wall and curtain surfaces are useful; plain wall/floor areas, ceiling, transitions and edges remain incomplete, with scattered outliers. Some sparse-depth diagnostics disagree (for example rank 480 has ~8.2% median relative discrepancy in the full run). Shared-pose consistency does not verify dimensions or complete architectural boundaries. **Do not force a closed room mesh or dimensioned polygon from these artifacts.**

The offline learned experiment is `outputs/learned-depth-six-v1`. It uses existing proto-1 CPU assets through `cozmo_reconstruction.dense.learned_compare`; no new model download or dependency was added to the default dense runtime. MapAnything code pin `3d10cf7a3016fc0f9bb13a071ee66c47b10be0d9`, checkpoint revision `00f9c245bbcb60522d1ed7f9e9d88462c6e3f38a`, checkpoint SHA-256 `fa06c0fdccefc5048e072c85935d5789b1e36b307f3859033c17f9dcb9fd5201`, DINO encoder pin `7764ea0f912e53c92e82eb78a2a1631e92725fc8` and clean source status were checked. Existing Torch 2.8.0+cpu, four threads and 518×294 model grids were used. RGB/K/pose conditioning and scale flags were explicit; depth inputs disabled. Predicted cameras/K are diagnostic only, and no model pointmap or inferred camera replaces the source gauge. Source audits passed before/after. The experiment manifest is distinct from the COLMAP bundle and is not accepted by default `cozmo-dense --verify-only`.

For a closer diagnostic, stereo Z was nearest-resampled to the **same six views, actual 518×294 K grids, source poses and neighbor schedule**, without Z rescaling, then subjected to the identical independent acceptance rules. Stereo retained **34.6848%** versus learned **10.9873%**. Stereo has about 0.9–1.7% median sparse-depth discrepancies on these retained samples; the learned first group has ~6.6–7.8%, while bed-group coverage is near zero. This favors the current stereo baseline for further conservative surface inspection. It is not a general model or accuracy benchmark: stereo depth was originally estimated using the 100-view neighborhood, the learned model jointly saw six views, and backend masks/filters differ. CPU inference and GPU stereo times are not a speed comparison.

Local evidence: `outputs/dense-evidence/validation.json`, `comparison.json`, `single-room-dense-100.png` and `audit.log`. These generated/private artifacts are excluded from Git and distribution. Next proposed milestone: supported floor/wall surface hypotheses with image-linked evidence, furniture rejection, residuals and explicit missing spans. TSDF, floorplan, double-room reconstruction and HTTP integration remain unimplemented; physical accuracy and calibration assumptions remain unverified.

## Sources

The implementation follows [COLMAP's known-pose workflow](https://colmap.github.io/faq.html#reconstruct-sparse-dense-model-from-known-camera-poses), [dense array format](https://colmap.github.io/format.html#dense-reconstruction), and the [official 4.2.1 CUDA distribution](https://pypi.org/project/pycolmap-cuda12/4.2.1/). Runtime signatures/options were also inspected in installed 4.2.1 instead of assuming the current development documentation matches that pin. [Sparse contract/results](RECONSTRUCTION.md), [staged reconstruction plan](RECONSTRUCTION_PLAN.md).
