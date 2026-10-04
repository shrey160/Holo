# Holo capture ingestion prototype

Holo is a local application and Python package for validating complete **Sensor Recorder Pro 1.5/build 5 ARKit** exports and the **provided Stray-style dataset**. It prepares traceable inputs and automatically generates dense RGB stereo geometry with a rough floor plan and provisional ceiling estimate in the GPU runtime; the portable CPU runtime produces a labelled sparse preview for verified Sensor Recorder ARKit captures. Your recordings live in `test_data/iphn-17`; the separately provided captures live in `test_data/drive_download`. Both formats have their own parsing, association and verification rules.

The application has three tabs:

- **Capture guide:** phone settings, reference-object preparation, clockwise room walkthrough and export handoff, from [capture.md](capture.md).
- **Input & validation:** complete ZIP/file uploads, optional reference metadata/photo, progress, persistent history, verified downloads and automatic preprocessing/reconstruction. Existing prepared captures can start a separate reconstruction run.
- **Reconstruction:** published capture results with a rough generated plan, interactive RGB point cloud, display controls and downloads. [Native/Docker setup and interpretation](docs/reconstruction/RECONSTRUCTION_VIEWER.md). Open [the local reconstruction workspace](http://localhost:8000/#reconstruction).

Ingestion retains native RGB frame references, sensor values/timestamps, per-frame intrinsics and supplied camera-to-world poses. Sensor Recorder preprocessing selects native-grid views, checks image connections and preserves exact K/poses/native IMU. Automatic Holo and optional CLI reconstruction produce fixed-pose sparse geometry and independently checked RGB stereo depth/point clouds. LiDAR and grounding measurements remain excluded; automatic dense plans use provisional supported surfaces and a rectangle prior; CPU previews are coarse coverage envelopes; object localization and scale correction require further work. Room surfaces remain incomplete and dimensional accuracy unverified. [Preprocessing](docs/ingestion/PREPROCESSING.md), [sparse reconstruction](docs/reconstruction/RECONSTRUCTION.md), [dense setup/design/results](docs/reconstruction/DENSE_RECONSTRUCTION.md).

See [automatic workflow, system design, retry behavior and limitations](AUTOMATIC_RECONSTRUCTION.md).

**Known issue / error baseline (2026-10-04):** native dense reconstruction now completes, including a provisional 2.55 m ceiling, but its rough plan expanded to 4.54 Ã— 4.06 m compared with the earlier approximately 3.33 Ã— 3.85 m result. The root cause remains unresolved; the user requested documentation and a baseline commit before the fix. [Regression evidence and reproduction](NATIVE_DENSE_REGRESSION.md), [committed handoff](CONTEXT.md).

**Native dense reconstruction:** Windows/NVIDIA users can run the full RGB stereo â†’ surfaces â†’ rough plan/ceiling â†’ interactive 3D workflow without Docker using the official COLMAP CUDA executable alongside the existing Python environment. [Installer, configuration and verification](NATIVE_DENSE.md). Holo shows backend readiness, a quality selector, processing stages and provisional room/ceiling summaries. CPU-only installations still produce sparse previews with no ceiling estimate.

The product is **Holo**. Existing `cozmo-ingestion`, `cozmo_ingestion`, `cozmo_web` and `cozmo-*` command identifiers remain unchanged for compatibility.

The separate CPU `cozmo-grounding` diagnostic checks opening-reference corner poses and unconstrained size against fixed source cameras, with an offline editor and optional accepted-stereo/surface comparisons. Its reviewed v4 report incorporates the confirmed marks and thickness below 1 cm; controlled pixel-center, holdout and point-fitting experiments still fail the residual gate. No correction or exact floor height is claimed. [Grounding workflow](docs/grounding/GROUNDING.md), [reviewed investigation/results](docs/grounding/GROUNDING_DIAGNOSTICS.md), [subsequent structural plan](docs/grounding/GROUNDING_PLAN.md). Existing geometry remains unchanged.

The separate CPU `cozmo-surfaces` stage now proposes floor/wall planes from verified dense RGB and provides image-linked evidence, occupied patches and furniture/ambiguity flags. Surface identities remain unconfirmed and no floorplan is generated. [Surface design, commands and findings](docs/reconstruction/SURFACES.md).

The separate CPU `cozmo-boundaries` stage binds reviewed image regions to accepted surface samples and projects supported wall spans into a local floor frame. The verified single-room trial retains 11 floor cells and one approximately 0.599 source-estimated metre wall projection. Assistant architectural decisions remain hypotheses; missing coverage stays open, and no floor-wall junction, room corner, closed polygon or measured room dimensions are certified. [Commands, review contract and results](docs/reconstruction/PARTIAL_BOUNDARIES.md), [module ownership](src/cozmo_reconstruction/boundaries/README.md). Native and Docker execution use the existing reconstruction runtime; Holo HTTP integration remains subsequent work.

## Input modalities

[Three-modality ingestion design](INPUT_MODALITIES_PLAN.md) covers video, per-room photos and raw LiDAR exports. A modality-neutral `canonical-capture-2` schema is shared by the **Photos** and **LiDAR** CLI modes.

```shell
# Photos: one room folder or a parent of per-room folders (JPEG/PNG only).
uv run --locked cozmo-ingest --mode photos --source ../test_data/Room-1 \
  --output outputs/photos-room1 --room-label "Room 1" --reference outputs/a4-reference.json
uv run --locked cozmo-verify --capture outputs/photos-room1 --source ../test_data/Room-1
uv run --locked cozmo-verify --capture outputs/photos-room1   # portable bundle only

# LiDAR: inspected Stray-style raw-depth export; depth/confidence retained.
uv run --locked cozmo-ingest --mode lidar --source ../test_data/drive_download/single_room/c00a170fe1 \
  --output outputs/lidar-single-room --ffmpeg /path/to/ffmpeg
uv run --locked cozmo-verify --capture outputs/lidar-single-room --source ../test_data/drive_download/single_room/c00a170fe1
```

Photo bundles copy originals into `sources/`, record EXIF/orientation and derive room membership from preserved paths; no camera K/poses are invented and no scale is applied. LiDAR bundles retain raw `uint16` depth and optional `uint8` confidence with explicit `FORMAT_REFERENCE_ASSUMED` convention provenance, populate supplied per-frame K/poses, and keep geometry readiness `CONVENTIONS_UNVERIFIED` (no fusion or unit conversion). Holo exposes the modes as **Photos / Videos + intrinsics / Lidar**; Holo's Lidar upload and photo reconstruction are not implemented yet. Plain no-tracking video (dropped card 4) is not offered.

## Quick start: Docker

From `proto-2`, with Docker Desktop using Linux containers:

```shell
docker compose up --build --detach --wait
```

Open **http://localhost:8000**. The image includes Python, FFmpeg/FFprobe, CPU PyCOLMAP and the compiled frontend. Jobs and captures persist in the named `captures` volume. `docker compose down` stops the app and keeps its data; adding `--volumes` removes that data. Initial build needs network access; processing and the bundled UI run locally afterward.

See [WEB_SETUP.md](docs/web/WEB_SETUP.md) for ports, limits, storage, CLI container use and troubleshooting.

To show separately published plan/3D results, use the optional `compose.reconstruction.yaml` override. [Publisher and viewer setup](docs/reconstruction/RECONSTRUCTION_VIEWER.md). The standard compose command generates labelled sparse previews. Add `-f compose.gpu.yaml` after the reconstruction override for automatic dense RGB/surfaces/floor/walls/ceiling processing; see [the automatic runtime guide](AUTOMATIC_RECONSTRUCTION.md). Historical published results remain available.

## Quick start: native development

Prerequisites:

| Tool | Requirement |
|---|---|
| uv | 0.12.1 or newer; [installation](https://docs.astral.sh/uv/getting-started/installation/) |
| Python | 3.12 default; uv can obtain it if missing. Package allows 3.12Ã¢â‚¬â€œ3.14; executed checks used 3.12.14 |
| FFmpeg / FFprobe | Both discoverable through PATH, or explicit FFmpeg path with FFprobe alongside/on PATH; [downloads](https://ffmpeg.org/download.html) |
| Node / npm | Node 24 LTS for frontend development/build; not required for CLI-only use or running Docker |

Terminal 1, from `proto-2`:

```shell
uv sync --locked --extra web --extra reconstruct
uv run --locked --extra web --extra reconstruct cozmo-web --reload
```

Terminal 2, from `proto-2/frontend`:

```shell
npm ci
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api` to the Python server on port 8000. If Docker already owns that port, stop it or use native `--port 8001` and set `API_TARGET=http://127.0.0.1:8001` before starting Vite. PowerShell: `$env:API_TARGET='http://127.0.0.1:8001'`.

If media tools are absent from PATH, append `--ffmpeg "C:/tools/ffmpeg/bin/ffmpeg.exe"` to the server command, using your actual installed path. `FFMPEG_PATH` is also supported. Stop the native server before dependency/metadata changes and uv sync on Windows, where its executable can be locked.

For compiled native mode, run `npm run build` from `frontend`, then `uv run --locked --extra web --extra reconstruct cozmo-web` from `proto-2` and open port 8000. [Full setup/configuration](docs/web/WEB_SETUP.md), [frontend guide](frontend/README.md).

## CLI-only setup

From `proto-2`:

```shell
uv sync --locked
uv run --locked cozmo-ingest --help
uv run --locked cozmo-verify --help
```

uv creates this project's own `.venv`. The ingestion core has no third-party runtime dependencies; the default development group includes test/lint tooling. `--extra preprocess` adds NumPy/OpenCV for CLI preprocessing. `--extra web` includes preprocessing and API dependencies. Keep the needed extra on uv commands so a sync does not remove it.

`--extra reconstruct` adds pinned PyCOLMAP 4.2.1 for `cozmo-reconstruct`. It supports the automatic Holo worker and separate native/CPU Docker CLI stage. [Setup and output review](docs/reconstruction/RECONSTRUCTION.md).

`cozmo-dense` estimates RGB stereo depth using a separate Linux CUDA worker (`docker build --target dense`, then `docker run --gpus all`). The optional `dense` and `reconstruct` extras intentionally conflict because CPU/CUDA distributions provide the same module. Windows CPU can verify the resulting dense artifacts with `--extra reconstruct` and `--verify-only`; its wheel cannot run PatchMatch inference. [Commands and limitations](docs/reconstruction/DENSE_RECONSTRUCTION.md).

`uv.lock` fixes project dependency resolution, and `--locked` refuses stale metadata. The build backend is specified separately in `pyproject.toml`. Initial uncached setup needs network access; ingestion itself is offline. Nothing imports prototype-1 or a developer-specific Python path. Recreate environments on other machines; do not distribute `.venv`, `.uv-cache` or `node_modules`.

## Input workflow

1. Follow [capture.md](capture.md): iPhone 15 and above is recommended. Start outside the doorway, record one known-size object for 3Ã¢â‚¬â€œ5 seconds at the opening only, then capture doorways/walls and room connections continuously. Leave the object at the first entrance.
2. Preserve the complete original export. Sensor Recorder sessions include `meta.json`, `wide.mp4`, `arkit_pose.csv` and enabled sensor CSV sidecars; metadata/schema validation determines required streams. Do not trim/re-encode the MP4 or upload it alone.
3. In **Input & validation**, select one complete ZIP or the exported files from one session. Add a label, optional reference dimensions/time interval and a JPEG/PNG photo of the opening object (up to 10 MiB). The photo can be attached without declaring dimensions.
4. Follow upload progress, then server validation/verification. Inspect findings; original observations remain retained.
5. Download result JSON or a portable archive containing `raw/`, optional `annotations/` and `reference/`, `bundle/` and verification evidence. The reference photo and its video/hash binding are retained in `reference/`.
6. For a successful Sensor Recorder capture, click **Prepare reconstruction views**. Holo creates a separate job with selected frames, visual-connection checks, motion findings and a portable derived archive. Review weak connections before reconstruction; LiDAR and grounding measurements are excluded. Provided Stray-style captures currently support ingestion only.

The CLI accepts an extracted session folder. Reference annotations are optional and must bind to the exact video hash; see [capture_annotations/README.md](capture_annotations/README.md).

## Use the provided dataset

In **Input & validation**, upload one of the original archives from `../test_data/drive_download/zips/`: `single_room.zip`, `single_scan_floor_only.zip` or `single_scan_with_ceiling.zip`. Each contains one nested session and retains depth/confidence folders. ZIP uploads work in Docker and native development; the app does not depend on a host-specific dataset mount.

For CLI use, point to the extracted session itself:

```shell
uv run --locked cozmo-ingest --source ../test_data/drive_download/single_room/c00a170fe1 --output outputs/provided-single
uv run --locked cozmo-verify --capture outputs/provided-single --source ../test_data/drive_download/single_room/c00a170fe1
```

Do not attach the A4 declaration from your recordings to these captures: the provided dataset has no declared opening reference. Stray-style exports retain native acceleration values with unresolved units, per-frame K/poses and an explicitly audited initial-video discard. [Supported layouts and results](docs/ingestion/SUPPLIED_DATA.md).

## Repository map

| Location | Purpose | Folder guide |
|---|---|---|
| `src/` | Installed Python packages and dependency boundary | [Source map](src/README.md) |
| `src/cozmo_ingestion/` | Domain pipeline, records, bundle storage, reader and verifier | [Core](src/cozmo_ingestion/README.md) |
| `src/cozmo_ingestion/adapters/` | Version-specific video source parsing/schema validation | [Adapters](src/cozmo_ingestion/adapters/README.md) |
| `src/cozmo_ingestion/multimodal/` | `canonical-capture-2` contracts, photo adapter/media and catalog dispatch | [Input modalities](src/cozmo_ingestion/multimodal/README.md) |
| `src/cozmo_preprocessing/` | View selection, image matching, native IMU association and derived verification | [Preprocessing](src/cozmo_preprocessing/README.md) |
| `src/cozmo_reconstruction/` | Fixed-camera sparse tracks, model/feature audits and CLI publication | [Reconstruction](src/cozmo_reconstruction/README.md) |
| `src/cozmo_web/` | API, safe uploads, isolated jobs, persistence and exports | [Web service](src/cozmo_web/README.md) |
| `frontend/` | React/TypeScript/Vite application | [Frontend](frontend/README.md) |
| `tests/` | Behavioral cases and synthetic fixtures | [Tests](tests/README.md) |
| `capture_annotations/` | Hash-bound declarations for the two supplied recordings | [Annotations](capture_annotations/README.md) |
| `outputs/` | Ignored CLI bundles, web data, temporary files and local evidence | Generated at runtime; excluded from distributions |
| `dist/` | Ignored Python wheel/source archives | Generated by `uv build` |
| `Dockerfile`, `compose.yaml` | Build/runtime container configuration | [Docker setup](docs/web/WEB_SETUP.md#docker) |
| `pyproject.toml`, `uv.lock`, `.python-version` | Package, dependency and interpreter configuration | [Architecture](docs/architecture/ARCHITECTURE.md) |

Folder READMEs describe ownership and editing paths. Generated dependency/output/cache folders do not contain maintained source documentation.

## Design and evidence

The core pipeline owns parsing/normalization/transactional publication. The optional web service owns uploads, queued isolated workers and persistent job records. The frontend owns presentation. [ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) explains typed boundaries, protocols, lifecycle and extension points.

| Document | Purpose |
|---|---|
| [capture.md](capture.md) | Authoritative capture settings/protocol and future grounding approach |
| [WEB_SETUP.md](docs/web/WEB_SETUP.md) | Docker/native modes, environment variables, limits and operations |
| [WEB_RESULTS.md](docs/web/WEB_RESULTS.md) | Current Windows/Linux/browser/packaging observations and limitations |
| [PREPROCESSING.md](docs/ingestion/PREPROCESSING.md) | RGB/pose/IMU preprocessing contract, commands, architecture and verified results |
| [PREPROCESSING_REVIEW.md](docs/ingestion/PREPROCESSING_REVIEW.md), [RECONSTRUCTION_PLAN.md](docs/reconstruction/RECONSTRUCTION_PLAN.md) | Weak-link/revisit review and staged reconstruction research; first sparse trial executed |
| [RECONSTRUCTION.md](docs/reconstruction/RECONSTRUCTION.md) | Fixed-camera sparse CLI, native/Docker setup, source/track audits and actual trials |
| [SUPPLIED_DATA.md](docs/ingestion/SUPPLIED_DATA.md) | Provided Stray-style input contract, clock association and ingestion evidence |
| [INGESTION_RESULTS.md](docs/ingestion/INGESTION_RESULTS.md) | Original iOS ingestion/source-value verification |
| [REFACTOR_RESULTS.md](docs/archive/REFACTOR_RESULTS.md) | Historical modularization/uv packaging evidence |
| [INGESTION_PLAN.md](docs/ingestion/INGESTION_PLAN.md), [DOCKER_WEB_PLAN.md](docs/web/DOCKER_WEB_PLAN.md) | Earlier design/research rationale; not current execution status |
| [Overview.md](docs/archive/Overview.md) | Prototype context and inherited project assumptions |

Both actual captures (1,756 and 3,949 frames) passed native Windows and Linux Docker ingestion/download verification with identical manifests and all sixteen canonical artifact hashes. Thirty Python tests passed at P2W-002; four reference-photo cases brought P2PHOTO-001 to 34. The supplied-data extension adds seven tests (41 total); see [provided-dataset support](docs/ingestion/SUPPLIED_DATA.md) for current evidence. Frontend build and formatting checks passed. Windows used FFmpeg 8.1.2; Docker used 5.1.9. Historical bundles remain verifiable after explicit newline/path portability changes. See the evidence documents for the distinction between runtime success and accuracy.

Other OS/architectures, long captures, uncached clean-machine setup and sustained multi-client capacity remain unverified. The service is local/single-instance with one active worker, bounded uploads/queue and persistent storage; it has no automatic retention or multi-user authentication. Android, ordinary photo/video and measured-depth reconstruction remain future work. Stray-style RGB/calibration/pose/native-IMU ingestion is supported; depth/confidence are retained and hash-checked without being admitted to assisted RGB processing.

## Ingest and verify

Examples using this workspace's recordings; substitute your own complete exported folder when submitting/running elsewhere:

```shell
uv run --locked cozmo-ingest --source ../test_data/iphn-17/single_room --annotations capture_annotations/single_room.json --output outputs/my-single-run
uv run --locked cozmo-verify --capture outputs/my-single-run --source ../test_data/iphn-17/single_room
```

If FFmpeg is not on `PATH`, append `--ffmpeg "C:/tools/ffmpeg/bin/ffmpeg.exe"` on Windows, using the actual installed path. On macOS/Linux use the installed executable path. No developer-specific search location is built into the code.

`--annotations` is optional. The example declares a user-reported 0.210Ãƒâ€”0.297 m reference and a first-five-second candidate interval tied to the exact video SHA-256. A new video needs its own declaration/hash; it is valid to ingest without one. A declaration does not assert object visibility or apply scale.

Use a new output folder for every run. Source/output overlap and existing outputs are rejected. A failed run retains a sibling `<output>.ingest-<id>` folder with diagnostics; only a validated run is published at the final path. Unsupported export versions, stream schemas, units, axes and clock/count mismatches fail explicitly.

## Read a capture from Python

```python
from pathlib import Path
from cozmo_ingestion import CaptureReader, IngestionPipeline, IngestionRequest

result = IngestionPipeline().run(
    IngestionRequest(source=Path("raw/session"), output=Path("outputs/session"))
)
capture = CaptureReader(result.output, profile="ios_assisted_rgb")
frames = capture.records("frames")
calibration = capture.records("calibration")
poses = capture.records("poses")
declared_reference = capture.records("annotations")
```

`video_rgb` admits only RGB/media indexing. `ios_assisted_rgb` admits RGB, calibration, poses, independent sensor streams and declared scale-prior metadata. `ios_preprocessing` excludes annotations and reference photos; the preprocessing service further restricts its reads to RGB, calibration, poses, accelerometer and gyroscope. Measured depth and evaluation references are excluded from these profiles. The role boundary is an API allowlist; consumers must use this reader. `usage()` records admitted access. The separate integrity component also supports audit reads for the verifier.

Raw assets are referenced, not copied. Keep the original folder when transporting a bundle, or rebase it with `CaptureReader(bundle, source_root=raw_folder)`; source hashes are checked. Source and output currently need to share a filesystem volume for relative root hints. Hashes detect accidental changes; manifests are not signed authentication.

## Bundle contents

| Artifact | Purpose |
|---|---|
| `manifest.json`, `sources.json` | Schema, adapter, policy, capabilities, source/artifact identities and raw-root hints |
| `frames.csv` | Every frame's source identity, media timestamp, source time, calibration/pose links and tracking state |
| `calibration.jsonl`, `trajectory/source_poses.jsonl` | Native per-frame K and supplied camera-to-world poses; raw quaternion/translation retained |
| `imu/*.csv` | Unresampled native streams with source row/line and relative time; Stray combined IMU is available through `native_imu` without conversion |
| `trajectory/unassociated_source_poses.jsonl` | Stray-only: retained first pose whose RGB observation is discarded by normal decoding |
| `annotations.json` | User scale declarations/candidate frames; localization and scale estimation `NOT_RUN` |
| `cameras.json`, `clocks.json`, `provenance.json`, `source_metadata.json` | Coordinate/timing conventions, stream coverage, source comments and original metadata |
| `validation/report.json`, `validation/summary.md` | Structural checks, readiness and explicit quality/unknown findings |
| `runtime.json` | Execution timing, Python/tool versions and commands; excluded from deterministic content hashes |

`READY_WITH_FINDINGS` means the ingestion contract passed. Physical synchronization, cameraÃ¢â‚¬â€œIMU extrinsics and metric accuracy remain unverified. Raw-IMU VIO and RGB-D readiness are false. Frames reference the original MP4; ingestion does not export thousands of JPEGs, rotate pixels, select views or refine trajectories.

## Development and submission checks

```shell
uv run --locked --extra web --extra reconstruct python -m unittest discover -s tests -v
uv run --locked --extra web ruff check .
uv run --locked --extra web ruff format --check .
uv build
```

The full suite includes ingestion, preprocessing, sparse/dense reconstruction, surface evidence and web behavioral tests: **143 cases** cover source/geometry retention, input exclusions, image matching, dense consistency, plane/patch evidence, furniture ambiguity, child-run/export behavior and tamper rejection. Omitting optional extras skips their test modules. Synthetic exports and injected services cover contract boundaries; real recordings separately exercise actual processing. See [tests/README.md](tests/README.md) for focused/Linux commands. From `frontend`, run `npm run build` and `npm run format:check`.

For deterministic replay, ingest again to a sibling output folder and then run:

```shell
uv run --locked cozmo-verify --capture outputs/my-single-run --source ../test_data/iphn-17/single_room --replay outputs/my-single-replay
```

Replay compares manifests and all declared content hashes. Runtime timing is excluded. Changing raw-root layout alters recorded hints, so the equality check assumes equivalent source/output layout.

`uv build` produces a wheel and source archive in ignored `dist/`. The wheel contains ingestion, preprocessing, reconstruction (including dense modules) and web packages with CLI entry points; their numerical/backend/web dependencies remain optional, and frontend assets are built separately. The source archive includes frontend/npm lockfile, tests, Docker configuration, uv lockfile, capture declarations and module documentation. Neither includes videos, `.venv`, dependency/cache directories or generated bundles. Supply raw data separately. Default dense inference uses the separate CUDA target; the standalone CPU wheel exposes result verification. Docker app contains the compiled UI. Evidence: [web](docs/web/WEB_RESULTS.md), [preprocessing](docs/ingestion/PREPROCESSING.md), [dense reconstruction](docs/reconstruction/DENSE_RECONSTRUCTION.md).

The root `ingest.py`, `verify_capture.py` and `capture_reader.py` are thin compatibility entry points. Use `uv run --locked python ingest.py ...` for the old script command, and use `cozmo_ingestion` for new imports. All implementation lives under `src/`.

Android, ordinary video/photos, LiDAR decoding and floorplan extraction remain future stages. Fixed-pose sparse and RGB stereo iOS reconstruction are available through optional CLIs; incomplete surfaces require review. Preprocessing currently supports the inspected Sensor Recorder iOS contract; provided Stray-style captures remain ingestion-only.

## Optional Gaussian appearance

[Gaussian experiment](docs/appearance/GAUSSIANS.md) adds a separate trained appearance scene beside the existing rough plan and point cloud. CPU source preparation/publication use the main uv environment; GPU training uses an isolated pinned uv/Docker worker. Holo can view published scenes natively or through read-only Docker catalogs without GPU Python dependencies. Physical dimensions and structural coverage remain unverified.

The recorded single-room Gaussian trial is available in Holo: **Open Gaussian view** in Reconstruction. It uses 100,000 Gaussians, 90 training/10 photometric holdout views, and improves mean PSNR from 10.36 to 21.94 dB. The held-out views also contributed to stereo initialization; this is not independent geometry validation. Unseen viewpoints remain fragile; physical dimensions are unverified. The full Windows/Linux suite now passes 109 cases.

## Floorplan refinement and report references

[CPU floorplan refinement](docs/reconstruction/FLOORPLAN_OPTIMIZATION.md) adds a structure-focused layer, original-occupancy comparison and bounded robust line suggestions without new model downloads. [Final report notes](docs/archive/FINAL_REPORT_NOTES.md) record deferred Gaussian refinement and the approximate user-reported 2.6 m ceiling reference, stored separately in [evaluation annotations](evaluation_annotations/README.md). Physical dimensions remain unverified.


## Complete rough room plan

The Reconstruction tab now displays **Single room - complete rough plan**: a complete inferred rectangular outline, approximate entrance, about **3.2 Ã— 4.1 m** at source-estimated scale and the user-supplied **about 2.6 m ceiling**. SVG/JSON downloads and evidence comparison are available; RGB 3D is retained. This opt-in draft allows errors and does not establish physical accuracy. [Algorithm and native/Docker workflow](docs/reconstruction/FLOORPLAN_OPTIMIZATION.md).


The newest furnished rough plan corrects the entrance to the bottom left, adds approximate bed/desk/chair/wardrobe/folding-chair positions and a **provisional 2.53 m ceiling envelope estimate**. The supplied ~2.6 m measurement is a separate comparison reference. Holo offers matching 3D floor outlines and an estimated-height shortcut. [Method, assumptions and commands](docs/reconstruction/FLOORPLAN_OPTIMIZATION.md).
