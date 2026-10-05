# Fresh-capture runbook

The target is setup in under 15 minutes. **That clean-machine timing was not measured and is not claimed as passed.** Network transfer, Python packages and the ~415 MB native CUDA archive can exceed it. The prior native dense example took about 15.1 minutes of processing after setup; setup time and reconstruction latency are different measurements.

## Native Windows dense path

Install Git, [uv >=0.12.1](https://docs.astral.sh/uv/getting-started/installation/), and [FFmpeg/FFprobe](https://ffmpeg.org/download.html). FFmpeg's download page links Windows builds; put their `bin` folder on PATH or pass `--ffmpeg C:/path/to/ffmpeg.exe`. Install an NVIDIA driver compatible with the official COLMAP CUDA build. No GPU is needed for preview mode.

```powershell
git clone https://github.com/shrey160/Holo.git
cd Holo
uv sync --locked --extra web --extra reconstruct
./scripts/install-native-colmap.ps1
uv run --locked --extra web --extra reconstruct holo-run example_data/video/single_room.zip --output outputs/example-room --mode dense
```

Replace the ZIP with a fresh complete Sensor Recorder export. Use a **new** output folder for each capture; existing results are never overwritten. `holo-run` defaults to required dense processing and fails visibly if unavailable. `--mode preview` runs the CPU sparse path; it does not estimate a ceiling. `--ingest-only` verifies input only. Omitting `--mode` is not a promise of CPU dense processing.

The command owns the full path: safe extraction -> ingestion/source verification -> preprocessing/native K/pose audit -> sparse -> CUDA RGB stereo -> surfaces -> supported rough room/ceiling -> atomic viewer publication. Read `outputs/example-room/run-summary.json`, `result.json`, stage reports and `outputs/reconstructions/capture-example-room/rough-room.svg`. Errors retain inputs and record `error.json`/`phase.json`; the CLI does not silently substitute a successful sparse result for required dense.

## Optional Holo UI

Install [Node.js 24](https://nodejs.org/en/download). Build once:

```powershell
cd frontend
npm ci
npm run build
cd ..
$env:DATA_ROOT = (Resolve-Path outputs).Path
uv run --locked --extra web --extra reconstruct cozmo-web
```

Open `http://localhost:8000/#reconstruction` and select the generated result. Holo's upload route can also process a ZIP directly. For frontend development, run `npm run dev` in `frontend` and the Python server separately. CLI-only use does not require Node or a frontend build.

## Reproduce cached room/fix numbers without GPU

```powershell
uv run --locked --extra web --extra reconstruct python scripts/replay-submission.py --output outputs/replay-01
```

This validates the example ZIP/cache hashes and regenerates before/after JSON, SVG, sizes, areas, ceiling estimates and a same-cache repeat check. It does not replace a live cold capture or repeat acquisition. [Exact evidence boundaries](reproduction/README.md).

## Docker and incomplete tiers

```shell
docker compose up --build --detach --wait
```

The normal container produces CPU sparse previews. The GPU path uses `compose.yaml` + `compose.reconstruction.yaml` + `compose.gpu.yaml` and a compatible Docker NVIDIA runtime; consult the development setup notes. All provided commands use local processing.

Photos: `uv run --locked cozmo-ingest --mode photos --source path/to/photo-rooms --output outputs/photo-capture`. LiDAR: `uv run --locked --extra web cozmo-ingest --mode lidar --source path/to/export --output outputs/lidar-capture`. These commands **validate input only**. Do not use `--mode video` on `cozmo-ingest` for Sensor Recorder exports; that flag denotes the unfinished plain-video modality. Photo/LiDAR reconstruction cannot run in the walk-in test in this submission.
