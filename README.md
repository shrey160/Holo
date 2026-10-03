# Holo — capture ingestion prototype

Holo is a local application and Python package for validating complete **Sensor Recorder Pro 1.5/build 5 ARKit** exports. It prepares traceable inputs for later floor-plan processing. The current source adapter is verified on the supplied base-iPhone 17 single-room and double-room recordings.

The application has two tabs:

- **Capture guide:** phone settings, reference-object preparation, clockwise room walkthrough and export handoff, from [capture.md](capture.md).
- **Input & validation:** complete ZIP/file uploads, an optional grounding-object photo and known-size reference declaration, progress, persisted history, quality findings and verified JSON/portable capture downloads.

Ingestion retains native RGB frame references, sensor values/timestamps, per-frame intrinsics and supplied camera-to-world poses. Object localization, scale correction, preprocessing and reconstruction are future stages. Successful ingestion does not establish dimensional accuracy.

The product is **Holo**. Existing `cozmo-ingestion`, `cozmo_ingestion`, `cozmo_web` and `cozmo-*` command identifiers remain unchanged for compatibility.

## Quick start: Docker

From `proto-2`, with Docker Desktop using Linux containers:

```shell
docker compose up --build --detach --wait
```

Open **http://localhost:8000**. The image includes Python, FFmpeg/FFprobe and the compiled frontend. Jobs and captures persist in the named `captures` volume. `docker compose down` stops the app and keeps its data; adding `--volumes` removes that data. Initial build needs network access; processing and the bundled UI run locally afterward.

See [WEB_SETUP.md](WEB_SETUP.md) for ports, limits, storage, CLI container use and troubleshooting.

## Quick start: native development

Prerequisites:

| Tool | Requirement |
|---|---|
| uv | 0.12.1 or newer; [installation](https://docs.astral.sh/uv/getting-started/installation/) |
| Python | 3.12 default; uv can obtain it if missing. Package allows 3.12–3.14; executed checks used 3.12.14 |
| FFmpeg / FFprobe | Both discoverable through PATH, or explicit FFmpeg path with FFprobe alongside/on PATH; [downloads](https://ffmpeg.org/download.html) |
| Node / npm | Node 24 LTS for frontend development/build; not required for CLI-only use or running Docker |

Terminal 1, from `proto-2`:

```shell
uv sync --locked --extra web
uv run --locked --extra web cozmo-web --reload
```

Terminal 2, from `proto-2/frontend`:

```shell
npm ci
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api` to the Python server on port 8000. If Docker already owns that port, stop it or use native `--port 8001` and set `API_TARGET=http://127.0.0.1:8001` before starting Vite. PowerShell: `$env:API_TARGET='http://127.0.0.1:8001'`.

If media tools are absent from PATH, append `--ffmpeg "C:/tools/ffmpeg/bin/ffmpeg.exe"` to the server command, using your actual installed path. `FFMPEG_PATH` is also supported. Stop the native server before dependency/metadata changes and uv sync on Windows, where its executable can be locked.

For compiled native mode, run `npm run build` from `frontend`, then `uv run --locked --extra web cozmo-web` from `proto-2` and open port 8000. [Full setup/configuration](WEB_SETUP.md), [frontend guide](frontend/README.md).

## CLI-only setup

From `proto-2`:

```shell
uv sync --locked
uv run --locked cozmo-ingest --help
uv run --locked cozmo-verify --help
```

uv creates this project's own `.venv`. The core has no third-party runtime dependencies; the default development group includes test/lint tooling. `--extra web` installs the optional API dependencies. Keep that extra on uv commands while using the web app so a sync does not remove them.

`uv.lock` fixes project dependency resolution, and `--locked` refuses stale metadata. The build backend is specified separately in `pyproject.toml`. Initial uncached setup needs network access; ingestion itself is offline. Nothing imports prototype-1 or a developer-specific Python path. Recreate environments on other machines; do not distribute `.venv`, `.uv-cache` or `node_modules`.

## Input workflow

1. Follow [capture.md](capture.md): iPhone 15 and above is recommended. Start outside the doorway, record one known-size object for 3–5 seconds at the opening only, then capture doorways/walls and room connections continuously. Leave the object at the first entrance.
2. Preserve the complete original export. Supplied sessions include `meta.json`, `wide.mp4`, `arkit_pose.csv` and enabled sensor CSV sidecars; metadata/schema validation determines required streams. Do not trim/re-encode the MP4 or upload it alone.
3. In **Input & validation**, select one complete ZIP or the exported files from one session. Add a label, optional reference dimensions/time interval and a JPEG/PNG photo of the opening object (up to 10 MiB). The photo can be attached without declaring dimensions.
4. Follow upload progress, then server validation/verification. Inspect findings; original observations remain retained.
5. Download result JSON or a portable archive containing `raw/`, optional `annotations/` and `reference/`, `bundle/` and verification evidence. The reference photo and its video/hash binding are retained in `reference/`.

The CLI accepts an extracted session folder. Reference annotations are optional and must bind to the exact video hash; see [capture_annotations/README.md](capture_annotations/README.md).

## Repository map

| Location | Purpose | Folder guide |
|---|---|---|
| `src/` | Installed Python packages and dependency boundary | [Source map](src/README.md) |
| `src/cozmo_ingestion/` | Domain pipeline, records, bundle storage, reader and verifier | [Core](src/cozmo_ingestion/README.md) |
| `src/cozmo_ingestion/adapters/` | Version-specific source parsing/schema validation | [Adapters](src/cozmo_ingestion/adapters/README.md) |
| `src/cozmo_web/` | API, safe uploads, isolated jobs, persistence and exports | [Web service](src/cozmo_web/README.md) |
| `frontend/` | React/TypeScript/Vite application | [Frontend](frontend/README.md) |
| `tests/` | Behavioral cases and synthetic fixtures | [Tests](tests/README.md) |
| `capture_annotations/` | Hash-bound declarations for the two supplied recordings | [Annotations](capture_annotations/README.md) |
| `outputs/` | Ignored CLI bundles, web data, temporary files and local evidence | Generated at runtime; excluded from distributions |
| `dist/` | Ignored Python wheel/source archives | Generated by `uv build` |
| `Dockerfile`, `compose.yaml` | Build/runtime container configuration | [Docker setup](WEB_SETUP.md#docker) |
| `pyproject.toml`, `uv.lock`, `.python-version` | Package, dependency and interpreter configuration | [Architecture](ARCHITECTURE.md) |

Folder READMEs describe ownership and editing paths. Generated dependency/output/cache folders do not contain maintained source documentation.

## Design and evidence

The core pipeline owns parsing/normalization/transactional publication. The optional web service owns uploads, queued isolated workers and persistent job records. The frontend owns presentation. [ARCHITECTURE.md](ARCHITECTURE.md) explains typed boundaries, protocols, lifecycle and extension points.

| Document | Purpose |
|---|---|
| [capture.md](capture.md) | Authoritative capture settings/protocol and future grounding approach |
| [WEB_SETUP.md](WEB_SETUP.md) | Docker/native modes, environment variables, limits and operations |
| [WEB_RESULTS.md](WEB_RESULTS.md) | Current Windows/Linux/browser/packaging observations and limitations |
| [INGESTION_RESULTS.md](INGESTION_RESULTS.md) | Original iOS ingestion/source-value verification |
| [REFACTOR_RESULTS.md](REFACTOR_RESULTS.md) | Historical modularization/uv packaging evidence |
| [INGESTION_PLAN.md](INGESTION_PLAN.md), [DOCKER_WEB_PLAN.md](DOCKER_WEB_PLAN.md) | Earlier design/research rationale; not current execution status |
| [Overview.md](Overview.md) | Prototype context and inherited project assumptions |

Both actual captures (1,756 and 3,949 frames) passed native Windows and Linux Docker ingestion/download verification with identical manifests and all sixteen canonical artifact hashes. Thirty Python tests passed at P2W-002; four additional reference-photo cases bring the current Windows/Linux suite to 34. Frontend build and formatting checks passed. Windows used FFmpeg 8.1.2; Docker used 5.1.9. Historical bundles remain verifiable after explicit newline/path portability changes. See the evidence documents for the distinction between runtime success and accuracy.

Other OS/architectures, long captures, uncached clean-machine setup and sustained multi-client capacity remain unverified. The service is local/single-instance with one active worker, bounded uploads/queue and persistent storage; it has no automatic retention or multi-user authentication. Android, ordinary photo/video and LiDAR adapters remain future work.

## Ingest and verify

Examples using this workspace's recordings; substitute your own complete exported folder when submitting/running elsewhere:

```shell
uv run --locked cozmo-ingest --source ../test_data/iphn-17/single_room --annotations capture_annotations/single_room.json --output outputs/my-single-run
uv run --locked cozmo-verify --capture outputs/my-single-run --source ../test_data/iphn-17/single_room
```

If FFmpeg is not on `PATH`, append `--ffmpeg "C:/tools/ffmpeg/bin/ffmpeg.exe"` on Windows, using the actual installed path. On macOS/Linux use the installed executable path. No developer-specific search location is built into the code.

`--annotations` is optional. The example declares a user-reported 0.210×0.297 m reference and a first-five-second candidate interval tied to the exact video SHA-256. A new video needs its own declaration/hash; it is valid to ingest without one. A declaration does not assert object visibility or apply scale.

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

`video_rgb` admits only RGB/media indexing. `ios_assisted_rgb` admits RGB, calibration, poses, independent sensor streams and declared scale-prior metadata. Measured depth and evaluation references are excluded from both. The role boundary is an API allowlist; consumers must use this reader. `usage()` records admitted access. The separate integrity component also supports audit reads for the verifier.

Raw assets are referenced, not copied. Keep the original folder when transporting a bundle, or rebase it with `CaptureReader(bundle, source_root=raw_folder)`; source hashes are checked. Source and output currently need to share a filesystem volume for relative root hints. Hashes detect accidental changes; manifests are not signed authentication.

## Bundle contents

| Artifact | Purpose |
|---|---|
| `manifest.json`, `sources.json` | Schema, adapter, policy, capabilities, source/artifact identities and raw-root hints |
| `frames.csv` | Every frame's source identity, media timestamp, source time, calibration/pose links and tracking state |
| `calibration.jsonl`, `trajectory/source_poses.jsonl` | Native per-frame K and supplied camera-to-world poses; raw quaternion/translation retained |
| `imu/*.csv` | Unresampled native streams with source row/line and relative time; combined IMU retained for audit |
| `annotations.json` | User scale declarations/candidate frames; localization and scale estimation `NOT_RUN` |
| `cameras.json`, `clocks.json`, `provenance.json`, `source_metadata.json` | Coordinate/timing conventions, stream coverage, source comments and original metadata |
| `validation/report.json`, `validation/summary.md` | Structural checks, readiness and explicit quality/unknown findings |
| `runtime.json` | Execution timing, Python/tool versions and commands; excluded from deterministic content hashes |

`READY_WITH_FINDINGS` means the ingestion contract passed. Physical synchronization, camera–IMU extrinsics and metric accuracy remain unverified. Raw-IMU VIO and RGB-D readiness are false. Frames reference the original MP4; ingestion does not export thousands of JPEGs, rotate pixels, select views or refine trajectories.

## Development and submission checks

```shell
uv run --locked --extra web python -m unittest discover -s tests -v
uv run --locked --extra web ruff check .
uv run --locked --extra web ruff format --check .
uv build
```

The full suite includes core and web behavioral tests; omitting the web extra skips web tests. The current 34 cases passed on Windows and Linux, including photo transport, validation and integrity checks. Synthetic exports and injected media/job services cover contract boundaries; real recordings separately exercise complete FFprobe/FFmpeg processing. See [tests/README.md](tests/README.md) for module coverage and focused/Linux commands. From `frontend`, run `npm run build` and `npm run format:check` for frontend checks.

For deterministic replay, ingest again to a sibling output folder and then run:

```shell
uv run --locked cozmo-verify --capture outputs/my-single-run --source ../test_data/iphn-17/single_room --replay outputs/my-single-replay
```

Replay compares manifests and all declared content hashes. Runtime timing is excluded. Changing raw-root layout alters recorded hints, so the equality check assumes equivalent source/output layout.

`uv build` produces a wheel and source archive in ignored `dist/`. The wheel contains both Python packages and CLI entry points; web dependencies remain optional, and frontend assets are built separately. The source archive also includes frontend source/npm lockfile, tests, Docker configuration, uv lockfile, capture declarations and folder documentation. Neither includes videos, `.venv`, dependency/cache directories or generated bundles. Raw recording data must be supplied separately. Docker contains the compiled UI. Detailed packaging evidence is in [WEB_RESULTS.md](WEB_RESULTS.md).

The root `ingest.py`, `verify_capture.py` and `capture_reader.py` are thin compatibility entry points. Use `uv run --locked python ingest.py ...` for the old script command, and use `cozmo_ingestion` for new imports. All implementation lives under `src/`.

Android, ordinary video/photos, LiDAR decoding, preprocessing and reconstruction are not implemented adapters/stages yet.
