# Holo capture workspace setup

**Current automatic workflow (2026-10-04):** For automatic reconstruction, native installs need both `--extra web --extra reconstruct`; the app Docker image includes both. `RECONSTRUCTION_TIMEOUT_SECONDS` defaults to 1800 for automatic/reconstruction jobs; the ingestion-only deadline stays 600. [Workflow, writable publication and retry contract](../../AUTOMATIC_RECONSTRUCTION.md).


The web extra/image includes NumPy and headless OpenCV for Sensor Recorder preprocessing. Existing Docker/native startup commands remain valid. From a verified capture, **Prepare reconstruction views** queues an independent derived run through the same worker/deadline. Its download includes `preprocessing/`. Standalone native preprocessing needs `uv sync --locked --extra preprocess` and FFmpeg. [Contract and evidence](../ingestion/PREPROCESSING.md).

The application has **Capture guide**, **Input & validation** and **Reconstruction** tabs. The reconstruction tab displays separately published rough plan/3D assets; [publication and mounting setup](../reconstruction/RECONSTRUCTION_VIEWER.md). Upload one complete Sensor Recorder export ZIP, or select its exported files together. Optional reference dimensions are recorded as hash-bound metadata; the form does not estimate geometry. An optional JPEG/PNG grounding-object photo (up to 10 MiB, 40 million pixels) can be attached independently of dimensions. Its encoding/full decode is checked in the worker, its original bytes are retained and its SHA-256 is bound to the video. Processing runs in an isolated child process and succeeds only after the source-value verifier passes. Download report JSON or a portable archive containing `raw/`, optional `annotations/` and `reference/`, `bundle/` and verification evidence. Verified results show the saved photo; reference-image integrity is rechecked before serving reports/images/archives.

## Docker

From `proto-2`, with Docker Desktop using Linux containers:

```shell
docker compose up --build --detach --wait
```

Open **http://localhost:8000**. Python, FFmpeg/FFprobe and compiled frontend assets are included. One non-root application service stores jobs and captures in the named `captures` volume. `docker compose down` keeps the volume; adding `--volumes` removes its capture data. To change host port/limits, copy `.env.example` to `.env` and edit values. Initial build needs network access; the bundled UI and capture processing run locally afterward.

The image also includes `cozmo-ingest` and `cozmo-verify`. For CLI runs, bind-mount raw input and writable output under the same container filesystem and use container paths. Windows host paths are not Linux process paths. [Verification](WEB_RESULTS.md), [design plan](DOCKER_WEB_PLAN.md).

## Native development, without Docker

Prerequisites: uv, Python 3.12, FFmpeg/FFprobe ([CLI setup](../../README.md)), and Node 24 LTS/npm for frontend tooling. Terminal 1, from `proto-2`:

```shell
uv sync --locked --extra web --extra reconstruct
uv run --locked --extra web --extra reconstruct cozmo-web --reload
```

Terminal 2, from `proto-2/frontend`:

```shell
npm ci
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api` to the native API at `127.0.0.1:8000`; frontend/Python source changes reload. Stop Docker first if it owns port 8000, or run the native API with `--port 8001` and set `API_TARGET=http://127.0.0.1:8001` in the frontend terminal. PowerShell: `$env:API_TARGET='http://127.0.0.1:8001'`.

If media tools are absent from PATH, append `--ffmpeg "C:/tools/ffmpeg/bin/ffmpeg.exe"` to the server command, using your actual path. `FFMPEG_PATH` is also supported. Native `.env` loading is not automatic: set variables in your terminal. Native data defaults to ignored `outputs/web-data`; `DATA_ROOT` changes it. Temporary uploads also live beneath that root, which only one server may own.

For compiled native mode, run `npm run build` from `frontend`, then `uv run --locked --extra web --extra reconstruct cozmo-web` from `proto-2` and open port 8000. The CLI detects `frontend/dist`; wheel users may point `STATIC_ROOT` to a separately built frontend. The wheel contains the core and optional API; frontend source is shipped in the source archive and built assets in Docker, rather than embedded in the wheel.

Keep `--extra web` on uv commands while running the application, so syncing does not remove optional dependencies. Core CLI-only installation still needs no third-party runtime packages. Successful output folders and original input files are not overwritten. Interrupted active jobs become failed; resubmit for a fresh run. Completed history and untouched queued jobs persist across restarts.

Stop the native server before changing Python dependencies/project metadata and syncing, particularly on Windows where a running executable can be locked. Restart it after `uv sync --locked --extra web`. Source-code edits alone use reload.

## Full automatic dense runtime

On Windows with NVIDIA GPU support, use the [native dense installer and setup](../../NATIVE_DENSE.md) to run without Docker, or use `docker compose -f compose.yaml -f compose.reconstruction.yaml -f compose.gpu.yaml up --build --detach --wait`. Docker keeps the same capture volume and adds the isolated CUDA PyCOLMAP app environment. CPU-only installations remain labelled sparse previews. Native supported Linux can use `uv sync --locked --extra web --extra dense`; do not combine dense and reconstruct extras. See [runtime, ownership and failure handling](../../AUTOMATIC_RECONSTRUCTION.md).

## Configuration and boundaries

| Variable | Default | Meaning |
|---|---|---|
| `DATA_ROOT` | Native `outputs/web-data`; Docker `/data` | Managed job/input/output storage |
| `FFMPEG_PATH` | PATH discovery | FFmpeg executable; FFprobe also required |
| `STATIC_ROOT` | Bundled static path or detected `frontend/dist` | Compiled frontend |
| `MAX_UPLOAD_BYTES` | 1,073,741,824 | Complete HTTP request limit |
| `MAX_EXPANDED_BYTES` | 2,147,483,648 | Expanded capture byte limit |
| `MAX_ARCHIVE_MEMBERS` | 25000 | ZIP entry/file selection limit |
| `MAX_QUEUED_JOBS` | 4 | Waiting capacity plus one active slot |
| `JOB_TIMEOUT_SECONDS` | 600 | Ingestion-only worker deadline |
| `RECONSTRUCTION_TIMEOUT_SECONDS` | 3600 | Automatic/reconstruction worker deadline |
| `RECONSTRUCTION_MODE` | auto | Dense if usable CUDA, otherwise labelled preview; dense requires CUDA; preview explicitly uses sparse |
| `COLMAP_EXECUTABLE` | PATH / project-local installation | Optional official COLMAP 4.2.1 CUDA executable for native dense stereo with CPU Python bindings |
| `APP_PORT` | 8000 | Compose host port only |
| `API_TARGET` | `http://127.0.0.1:8000` | Vite proxy target only |

These are admission limits, not measured long-capture capacity. Request bytes are bounded before multipart spooling; extraction checks cross-platform paths/collisions, links, declared/actual bytes and disk space. The supported domain includes Sensor Recorder Pro 1.5/build 5 ARKit sessions and the three provided Stray-style captures. The 25,000-member default accommodates their depth/confidence folders; ZIP requests remain bounded to 1 GiB with 2 GiB expanded data. See [provided-data support](../ingestion/SUPPLIED_DATA.md). Original observations, source poses and declared reference metadata are retained; physical accuracy and geometry remain unverified.

Completed/failed jobs persist until the operator manages the data directory; there is no automatic retention policy or multi-user authentication. Host ports bind to loopback for this local prototype. Do not run multiple application workers against one data root.

## Checks

From `proto-2`:

```shell
uv run --locked --extra web python -m unittest discover -s tests -v
uv run --locked --extra web ruff check .
uv run --locked --extra web ruff format --check .
docker compose config --quiet
```

From `frontend`: `npm run build` and `npm run format:check`. Core-only users may omit the web extra; web tests then skip. Docker image build, runtime health, actual ingestion correctness and geometry accuracy are distinct checks; [WEB_RESULTS.md](WEB_RESULTS.md) records observed outcomes and limits.

For the full Python suite in Linux: `docker build --target checks -t cozmo-ingestion-checks:0.2.0 .`. This separate build stage installs locked test dependencies and runs tests/lint; tests and development packages are excluded from the shipped runtime image.
# Reconstruction viewer

Holo's third tab displays published rough plans and interactive 3D point clouds. [Publisher command, native environment and read-only Docker override](../reconstruction/RECONSTRUCTION_VIEWER.md). For the supplied local trial use `docker compose -f compose.yaml -f compose.reconstruction.yaml up --build --detach --wait`; this keeps the existing captures volume. Native/Vite testing remains supported. New Sensor Recorder ARKit uploads reconstruct and publish automatically by default. Existing prepared jobs can create reconstruction children. [Workflow and limitations](../../AUTOMATIC_RECONSTRUCTION.md).

## Optional Gaussian scenes

Set `GAUSSIAN_ROOT` to a published Gaussian catalog alongside `RECONSTRUCTION_ROOT`. The reconstruction Compose override mounts both catalogs read-only; the standard captures volume is preserved. No GPU is needed for Holo viewing. Source preparation/publication and isolated GPU training are documented in [GAUSSIANS.md](../appearance/GAUSSIANS.md).
