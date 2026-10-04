# Holo

Holo is a local application and Python package for capturing a room with a phone and turning the
export into traceable geometry. It verifies a raw capture, selects reconstruction views, runs
fixed-pose sparse and dense RGB reconstruction, proposes floor and wall surfaces, and publishes a
rough single-room plan with an interactive 3D view. Everything runs on your own machine; no
candidate-owned service is required.

Demo walkthrough: <https://youtu.be/N7grapMf2BA>

There are two ways to use it:

- **The Holo app** - a FastAPI service and React/TypeScript frontend with a capture guide, upload
  and validation history, and a reconstruction viewer.
- **The command line** - `cozmo-*` tools for batch ingestion, preprocessing and reconstruction.

## What it does

- **Verifies the capture.** Parses a complete Sensor Recorder Pro ARKit export (or the provided
  Stray-style dataset), checks media/sensor counts and clocks, and writes a canonical, hash-bound
  bundle without altering the original files.
- **Prepares reconstruction views.** Selects native-grid frames by sharpness, texture and motion,
  checks visual connections, and exports exact per-frame intrinsics, camera-to-world poses and
  native IMU.
- **Reconstructs.** Triangulates fixed-camera sparse geometry, then estimates RGB stereo depth in a
  separate CUDA worker, and independently checks every candidate pixel against neighbouring views.
- **Estimates structure.** Proposes planar surfaces from the dense cloud, reviews image-linked
  evidence, and derives a provisional floor, rectangular wall hypothesis and ceiling envelope.
- **Publishes for review.** Emits a rough plan (SVG/JSON) and an interactive RGB point cloud, with
  atomic, hash-verified assets and downloads.

## Supported inputs

| Modality | Status |
|---|---|
| Assisted video (ARKit export with poses/intrinsics) | End-to-end reconstruction path |
| Room photos (JPEG/PNG, no poses/depth) | Ingestion and verification only |
| LiDAR raw depth + confidence + poses | Ingestion and verification only |
| Plain MP4 (no poses) | Not supported; rejected explicitly |

The tested capture device is a non-LiDAR iPhone (ARKit export), and the tested processing machine is
Windows/NVIDIA. See [device matrix](submission/DEVICE_MATRIX.md) for exact versions and boundaries.

## Requirements

| Tool | Requirement |
|---|---|
| uv | 0.12.1 or newer ([install](https://docs.astral.sh/uv/getting-started/installation/)) |
| Python | 3.12 default (uv can install it); package allows 3.12-3.14 |
| FFmpeg / FFprobe | On `PATH`, or pass `--ffmpeg` with FFprobe alongside |
| Node / npm | Node 24 LTS only for frontend development (not needed for the CLI or Docker) |
| NVIDIA GPU + driver | Optional; required for dense RGB stereo (CPU runs sparse previews) |

## Quick start: Docker

From `proto-2`, with Docker Desktop on Linux containers:

```shell
docker compose up --build --detach --wait
```

Open <http://localhost:8000>. The image bundles Python, FFmpeg, CPU PyCOLMAP and the compiled
frontend. Captures persist in the named `captures` volume; `docker compose down` keeps them,
`--volumes` removes them.

For automatic dense reconstruction (floor/walls/ceiling), add the reconstruction and GPU overlays:

```shell
docker compose -f compose.yaml -f compose.reconstruction.yaml -f compose.gpu.yaml up --build --detach --wait
```

See [web setup](docs/web/WEB_SETUP.md) for ports, limits, storage and troubleshooting, and
[automatic reconstruction](AUTOMATIC_RECONSTRUCTION.md) for the full workflow.

## Quick start: native development

```shell
uv sync --locked --extra web --extra reconstruct
uv run --locked --extra web --extra reconstruct cozmo-web --reload
```

In a second terminal, from `frontend`:

```shell
npm ci
npm run dev
```

Open <http://localhost:5173> (Vite proxies `/api` to the Python server on port 8000). If FFmpeg is
not on `PATH`, add `--ffmpeg "C:/path/to/ffmpeg.exe"`. For a compiled build, run `npm run build`,
then start `cozmo-web` and open port 8000. Windows/NVIDIA users can run the dense workflow without
Docker using the official COLMAP CUDA executable: see [native dense setup](NATIVE_DENSE.md).

## Command line

```shell
uv sync --locked                       # core ingestion/verification
uv sync --locked --extra reconstruct   # sparse + dense verification paths
uv sync --locked --extra dense         # Linux CUDA dense inference
```

| Command | Purpose |
|---|---|
| `holo-run` | One-command ingestion through publication for a capture ZIP |
| `cozmo-ingest` / `cozmo-verify` | Ingest (`--mode video`/`photos`/`lidar`) and audit a capture bundle |
| `cozmo-preprocess` | Select views from a verified capture and export K/poses/IMU |
| `cozmo-reconstruct` | Fixed-camera sparse reconstruction and audit |
| `cozmo-dense` | RGB stereo depth (separate CUDA worker) and verification |
| `cozmo-surfaces` | Planar surface hypotheses with image-linked evidence |
| `cozmo-grounding` | Opening-reference corner diagnostic |
| `cozmo-boundaries` | Reviewed partial floor/wall projections |
| `cozmo-publish-reconstruction` | Publish a plan/3D viewer result |
| `cozmo-gaussians` | Prepare/publish the optional Gaussian appearance scene |
| `cozmo-web` | Run the local web application |

Example - ingest and verify a capture export:

```shell
uv run --locked cozmo-ingest --source ../test_data/iphn-17/single_room \
  --annotations capture_annotations/single_room.json --output outputs/my-single-run
uv run --locked cozmo-verify --capture outputs/my-single-run --source ../test_data/iphn-17/single_room
```

The optional declaration binds a user-reported reference size to the exact video hash; it does not
apply scale or assert object visibility. Use a new output folder for every run. See
[input modalities](INPUT_MODALITIES_PLAN.md) and [provided dataset](docs/ingestion/SUPPLIED_DATA.md).

## Repository layout

| Location | Purpose |
|---|---|
| `src/cozmo_ingestion/` | Capture pipeline, records, bundle storage, reader and verifier |
| `src/cozmo_preprocessing/` | View selection, image matching, IMU association |
| `src/cozmo_reconstruction/` | Sparse, dense, surfaces, grounding, boundaries and viewer |
| `src/cozmo_web/` | API, safe uploads, isolated jobs, persistence and exports |
| `frontend/` | React/TypeScript/Vite application |
| `tests/` | Behavioural tests and synthetic fixtures |
| `docs/` | Detailed documentation, grouped by topic ([index](docs/README.md)) |
| `capture_annotations/`, `evaluation_annotations/` | Hash-bound declarations and user references |
| `experiments/` | Isolated experiments (e.g. Gaussian training worker) |
| `example_data/`, `submission/` | Example capture and submission bundle |
| `outputs/` | Generated bundles and local evidence (ignored) |
| `Dockerfile`, `compose*.yaml`, `pyproject.toml`, `uv.lock` | Build and dependency configuration |

`capture_reader.py`, `ingest.py` and `verify_capture.py` at the root are thin compatibility entry
points; all implementation lives under `src/`.

## Documentation

| Document | Contents |
|---|---|
| [Repository docs index](docs/README.md) | Map of everything under `docs/` |
| [Capture protocol](capture.md) | Phone settings, walkthrough and export handoff |
| [Architecture](docs/architecture/ARCHITECTURE.md) | Package boundaries, lifecycle and extension points |
| [Automatic reconstruction](AUTOMATIC_RECONSTRUCTION.md) | Upload-to-plan workflow and state handling |
| [Native dense setup](NATIVE_DENSE.md) | Windows/NVIDIA dense path without Docker |
| [Preprocessing](docs/ingestion/PREPROCESSING.md) | RGB/pose/IMU preparation contract and results |
| [Sparse](docs/reconstruction/RECONSTRUCTION.md) / [dense](docs/reconstruction/DENSE_RECONSTRUCTION.md) | Reconstruction stages and audits |
| [Surfaces](docs/reconstruction/SURFACES.md) / [boundaries](docs/reconstruction/PARTIAL_BOUNDARIES.md) | Plane hypotheses and reviewed wall spans |
| [Floorplan refinement](docs/reconstruction/FLOORPLAN_OPTIMIZATION.md) / [viewer](docs/reconstruction/RECONSTRUCTION_VIEWER.md) | Rough plan and 3D presentation |
| [Grounding](docs/grounding/GROUNDING.md) / [reviewed investigation](docs/grounding/GROUNDING_DIAGNOSTICS.md) | Opening-reference calibration diagnostic |
| [Web setup](docs/web/WEB_SETUP.md) / [results](docs/web/WEB_RESULTS.md) | Docker/native operation and evidence |
| [Gaussian appearance](docs/appearance/GAUSSIANS.md) | Optional appearance experiment |
| [Submission bundle](submission/README.md) | Compliance matrix, device matrix, runbook and reports |

## Development

```shell
uv run --locked --extra web --extra reconstruct python -m unittest discover -s tests -v
uv run --locked --extra web ruff check .
uv run --locked --extra web ruff format --check .
uv build
```

From `frontend`, run `npm run build` and `npm run format:check`. See [tests](tests/README.md) for
focused and Linux commands. `uv build` writes a wheel and source archive to the ignored `dist/`;
neither includes captures, environments or generated bundles.

## Status and limitations

Holo produces a rough, uncalibrated single-room sketch, not a survey. Source poses are treated as
fixed and no drift correction or loop closure is applied, so absolute dimensions are unverified. The
plan, doorway and ceiling are provisional hypotheses; occlusion can make them too small and
furniture can make them too large. Photos and LiDAR are ingested but not reconstructed, and
multi-room stitching and damage/scope output are not implemented. A native dense floor-plan
regression was found and corrected - the baseline and comparison remain in
[the regression evidence](docs/regressions/native-dense-2026-10-04/README.md) and
[the fix write-up](NATIVE_FLOOR_PLAN_FIX.md).
