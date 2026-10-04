# Gaussian appearance experiment

**Further work deferred by user, 2026-10-04.** The bounded trial below already completed; additional downloads, optimization and splatting-specific improvements are stopped so work can return to floorplans. Existing results remain separate appearance evidence. [Final report notes](../archive/FINAL_REPORT_NOTES.md).

This optional stage trains a visual room representation from verified RGB views, camera intrinsics and fixed source poses. It does not replace stereo, source-image region reviews, partial boundaries or calibration. [Current reconstruction viewer](../reconstruction/RECONSTRUCTION_VIEWER.md).

## Design and boundaries

The CPU `cozmo-gaussians prepare` command audits the complete boundary/surface/dense/sparse/prepared/ingestion/source chain before publishing bounded GPU inputs. Images are resized with their per-frame intrinsics; world coordinates and camera poses remain unchanged. Initial Gaussians sample the accepted stereo cloud deterministically. No captured LiDAR, grounding geometry, IMU integration, pose optimization or scene normalization is used.

Training runs in a separate uv virtual environment: Python 3.10, PyTorch 2.4.1/CUDA 12.4 and the official precompiled gsplat 1.5.3 wheel. Holo's main Python 3.12 environment and ordinary application container do not install Torch or require a GPU. Dependencies are isolated in [the experiment project](../../experiments/gsplat/pyproject.toml); the [worker](../../experiments/gsplat/worker.py) implements a deliberately bounded first trial rather than reproducing the complete upstream trainer.

The worker optimizes Gaussian positions, anisotropic scales, rotations, opacity and view-independent RGB. Cameras and their scale remain fixed; learned Gaussian geometry is an appearance derivative, not newly certified structural geometry. The trial uses a fixed Gaussian count, no densification, SH degree zero, L1 plus local SSIM loss, bounded scales, a step limit and wall-clock deadline. Seed 42 controls initialization/view sampling; CUDA bitwise determinism is not claimed.

One in ten source views is excluded from appearance training. Validation compares initial and trained renderings against the exact same withheld images using PSNR, local-window SSIM and opacity coverage. **Stereo initialization uses all source views. This is a photometric holdout, not an independent geometry or unseen-capture benchmark.** Improvements over initial Gaussians do not establish superiority over another trained method or the point-cloud viewer.

The CPU publisher requires completed fixed-camera training, matching input/viewer source identities and a mean photometric holdout gain exceeding 1 dB. It verifies finite arrays, valid scales, a proper rigid floor transform and all declared hashes, then atomically publishes a separate scene. Originals and structural viewer assets are never overwritten. The standard `.splat` asset stores 32 bytes per Gaussian: position, scale, RGBA and normalized wxyz quaternion encoded to bytes. Rotation includes the rigid floor-frame transform, preserving anisotropic covariance orientation; quaternion/color quantization makes browser rendering an approximation of training renders.

Holo uses [GaussianSplats3D](https://github.com/mkkellogg/GaussianSplats3D) 0.4.7 to render the downloadable scene locally in WebGL. The renderer loads on demand, initializes the source camera before loading, uses CPU sorting with transferable worker buffers (no cross-origin SharedArrayBuffer requirement), and releases resources on close/tab changes. Viewing needs no GPU Python server. This first version exposes orbit/pan/zoom, reset, a source-versus-render comparison and report/scene downloads. Missing coverage and furniture remain visible; no mesh, floorplan closure or dimensional correction is inferred.

## Reproduce

Install the ordinary CPU preparation/publication dependencies:

```shell
uv sync --locked --extra web --extra reconstruct
cozmo-gaussians prepare outputs/single-room-boundaries-v1 outputs/gsplat-evidence/inputs-v1 --surfaces outputs/single-room-surfaces-v2 --sparse outputs/single-room-sparse-100-v2 --prepared outputs/single-room-preprocessing-final --bundle outputs/single-room-cli-v2 --dense outputs/linux-reconstruction/single-room-dense-100-v1 --source ../test_data/iphn-17/single_room --grounding outputs/single-room-grounding-v4
docker build -t holo-gsplat:0.1.0 experiments/gsplat
docker run --rm --gpus all --mount "type=bind,source=ABSOLUTE_INPUTS,target=/inputs,readonly" --mount "type=bind,source=ABSOLUTE_EXPERIMENT_PARENT,target=/results" holo-gsplat:0.1.0 /inputs /results/trial-v4-10k --steps 10000 --deadline 900
cozmo-gaussians publish outputs/gsplat-evidence/inputs-v1 outputs/gsplat-evidence/trial-v4-10k outputs/holo-reconstruction/single-room-v1 outputs/holo-gaussians/single-room-v1
```

Use `uv run --locked --extra reconstruct cozmo-gaussians ...` if the main venv is not activated. Substitute existing verified inputs and absolute mount paths. All published outputs must be new folders; failed/partial trial folders are retained for diagnosis. Training requires compatible NVIDIA hardware/driver. For native Linux GPU training, `uv sync --locked` in `experiments/gsplat` and `uv run --locked python worker.py INPUTS NEW_OUTPUT` use the same isolated environment; ordinary native Holo development remains available without Docker or CUDA.

For Holo, set `RECONSTRUCTION_ROOT` to the structural viewer catalog and `GAUSSIAN_ROOT` to the separate Gaussian catalog. Native example: `GAUSSIAN_ROOT=outputs/holo-gaussians`. Docker [the reconstruction override](../../compose.reconstruction.yaml) mounts both catalogs read-only and preserves the captures volume:

```shell
docker compose -f compose.yaml -f compose.reconstruction.yaml up --build --detach --wait
```

Open [Reconstruction](http://localhost:8000/#reconstruction), then **Open Gaussian view**. The optional section appears only for a published scene bound to the selected reconstruction. `/api/gaussians` and fixed allowlisted asset endpoints verify hashes and the parent reconstruction identity; they accept no arbitrary host paths and do not train models over HTTP.

## Validation and limits

The implementation tests cover rigid position/covariance orientation, binary layout, invalid geometry/scaling, bounded admission, source mismatch, publication quality gates, no overwrite, hash-checked HTTP and preservation of upstream files. The full suite passes **109 tests on Windows and Linux**. CUDA forward/backward kernels pass in the final pinned image. Native and Docker catalogs return identical scenes; all five Gaussian and eight structural assets pass HTTP SHA-256 checks on both. Orbit/zoom/reset, close/reopen and tab-change cleanup were exercised in Holo without console errors. All 1,510 protected raw/upstream/report/viewer files and the 10 existing capture jobs remain unchanged. The source archive and wheel include the CPU modules/entry point and isolated worker source, while excluding raw captures, experiment results, virtual environments and caches. Physical room dimensions, calibration mismatch, unsupported walls and double-room topology remain unresolved.

Primary references: [gsplat](https://github.com/nerfstudio-project/gsplat), [COLMAP example](https://docs.gsplat.studio/main/examples/colmap.html), [rasterization API](https://docs.gsplat.studio/main/apis/rasterization.html), [official wheel matrix](https://docs.gsplat.studio/whl/gsplat/). Main-branch documentation includes newer features; this experiment deliberately uses the pinned release and its installed API.

## Recorded single-room trial (2026-10-04)

100 audited views at 640Ã—360; 90 training views and 10 photometric holdouts. Both runs use the same 100,000 stereo-initialized Gaussians and fixed source cameras/scale. The initial mean is 10.36 dB PSNR / 0.353 local SSIM.

| Trial | Steps | Mean holdout PSNR | Mean local SSIM | Training/evaluation elapsed |
|---|---:|---:|---:|---:|
| `trial-v3` | 3,000 | 20.50 dB | 0.754 | 23.51 s |
| `trial-v4-10k` (published) | 10,000 | 21.94 dB | 0.789 | 68.51 s |

Measured on the RTX 4060 Laptop GPU; peak Torch-allocated memory was 356,088,320 bytes (about 340 MiB), excluding driver/context and total GPU memory. Elapsed timings exclude the first dependency download/image build. Several sampled paired renderings were visually reviewed; the longer fit improves detail modestly and is published separately at `outputs/holo-gaussians/single-room-v1`. Its portable 32-byte scene is 3.2 MB. The browser resets to an actual mid-capture camera rather than an exterior overview.

The model is useful for inspecting captured appearance. Fine details remain soft and moving far from source viewpoints can blur, tear or expose gaps. Mean quality is not a minimum per-view guarantee; the report retains every held-out score. This is no evidence of calibrated physical accuracy, new architectural acceptance, room closure or better geometry than the stereo baseline. Double-room training and automatic upload-to-reconstruction remain unimplemented.

Private evidence under `outputs/gsplat-evidence/` includes the selected training report, source preservation and native/Docker delivery checks, package/link verification and a Holo screenshot. Outputs are excluded from distribution. Reproduction commands require existing verified upstream results and a **new output folder**; the recorded folders already exist and are intentionally not overwritten.
