# Holo capture workspace setup

The web extra/image includes NumPy and headless OpenCV for Sensor Recorder preprocessing. Existing Docker/native startup commands remain valid. From a verified capture, **Prepare reconstruction views** queues an independent derived run through the same worker/deadline. Its download includes `preprocessing/`. Standalone native preprocessing needs `uv sync --locked --extra preprocess` and FFmpeg. [Contract and evidence](PREPROCESSING.md).

The application has **Capture guide** and **Input & validation** tabs. Upload one complete Sensor Recorder export ZIP, or select its exported files together. Optional reference dimensions are recorded as hash-bound metadata; the form does not estimate geometry. An optional JPEG/PNG grounding-object photo (up to 10 MiB, 40 million pixels) can be attached independently of dimensions. Its encoding/full decode is checked in the worker, its original bytes are retained and its SHA-256 is bound to the video. Processing runs in an isolated child process and succeeds only after the source-value verifier passes. Download report JSON or a portable archive containing `raw/`, optional `annotations/` and `reference/`, `bundle/` and verification evidence. Verified results show the saved photo; reference-image integrity is rechecked before serving reports/images/archives.

## Docker

From `proto-2`, with Docker Desktop using Linux containers:

```shell
docker compose up --build --detach --wait
```

Open **http://localhost:8000**. Python, FFmpeg/FFprobe and compiled frontend assets are included. One non-root application service stores jobs and captures in the named `captures` volume. `docker compose down` keeps the volume; adding `--volumes` removes its capture data. To change host port/limits, copy `.env.example` to `.env` and edit values. Initial build needs network access; the bundled UI and capture processing run locally afterward.

The image also includes `cozmo-ingest` and `cozmo-verify`. For CLI runs, bind-mount raw input and writable output under the same container filesystem and use container paths. Windows host paths are not Linux process paths. [Verification](WEB_RESULTS.md), [design plan](DOCKER_WEB_PLAN.md).

## Native development, without Docker

Prerequisites: uv, Python 3.12, FFmpeg/FFprobe ([CLI setup](README.md)), and Node 24 LTS/npm for frontend tooling. Terminal 1, from `proto-2`:

```shell
uv sync --locked --extra web
uv run --locked --extra web cozmo-web --reload
```

Terminal 2, from `proto-2/frontend`:

```shell
npm ci
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api` to the native API at `127.0.0.1:8000`; frontend/Python source changes reload. Stop Docker first if it owns port 8000, or run the native API with `--port 8001` and set `API_TARGET=http://127.0.0.1:8001` in the frontend terminal. PowerShell: `$env:API_TARGET='http://127.0.0.1:8001'`.

If media tools are absent from PATH, append `--ffmpeg "C:/tools/ffmpeg/bin/ffmpeg.exe"` to the server command, using your actual path. `FFMPEG_PATH` is also supported. Native `.env` loading is not automatic: set variables in your terminal. Native data defaults to ignored `outputs/web-data`; `DATA_ROOT` changes it. Temporary uploads also live beneath that root, which only one server may own.

For compiled native mode, run `npm run build` from `frontend`, then `uv run --locked --extra web cozmo-web` from `proto-2` and open port 8000. The CLI detects `frontend/dist`; wheel users may point `STATIC_ROOT` to a separately built frontend. The wheel contains the core and optional API; frontend source is shipped in the source archive and built assets in Docker, rather than embedded in the wheel.

Keep `--extra web` on uv commands while running the application, so syncing does not remove optional dependencies. Core CLI-only installation still needs no third-party runtime packages. Successful output folders and original input files are not overwritten. Interrupted active jobs become failed; resubmit for a fresh run. Completed history and untouched queued jobs persist across restarts.

Stop the native server before changing Python dependencies/project metadata and syncing, particularly on Windows where a running executable can be locked. Restart it after `uv sync --locked --extra web`. Source-code edits alone use reload.

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
| `JOB_TIMEOUT_SECONDS` | 600 | Worker execution deadline |
| `APP_PORT` | 8000 | Compose host port only |
| `API_TARGET` | `http://127.0.0.1:8000` | Vite proxy target only |

These are admission limits, not measured long-capture capacity. Request bytes are bounded before multipart spooling; extraction checks cross-platform paths/collisions, links, declared/actual bytes and disk space. The supported domain includes Sensor Recorder Pro 1.5/build 5 ARKit sessions and the three provided Stray-style captures. The 25,000-member default accommodates their depth/confidence folders; ZIP requests remain bounded to 1 GiB with 2 GiB expanded data. See [provided-data support](SUPPLIED_DATA.md). Original observations, source poses and declared reference metadata are retained; physical accuracy and geometry remain unverified.

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
