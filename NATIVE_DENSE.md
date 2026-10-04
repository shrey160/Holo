# Native dense reconstruction on Windows

Holo can run its complete dense RGB workflow without Docker. Keep the portable CPU PyCOLMAP 4.2.1 package for camera models, sparse reconstruction, image undistortion and audits; install the official **COLMAP 4.2.1 Windows CUDA executable** for PatchMatch stereo. The official CUDA Python wheels are currently Linux-only ([PyCOLMAP documentation](https://colmap.github.io/pycolmap/index.html)). An NVIDIA CUDA device and driver are required. CPU-only machines retain the explicitly labelled sparse preview; it has no ceiling estimate.

## Setup

From `proto-2` in PowerShell:

```powershell
uv sync --locked --extra web --extra reconstruct
./scripts/install-native-colmap.ps1
# Optional when launching from another working directory:
$env:COLMAP_EXECUTABLE = (Resolve-Path .tools/colmap/bin/colmap.exe).Path
$env:RECONSTRUCTION_MODE = 'auto'
uv run --locked --extra web --extra reconstruct cozmo-web
```

The installer downloads the [official Windows CUDA archive](https://github.com/colmap/colmap/releases/tag/4.2.1), checks its release SHA-256, and extracts into ignored `.tools/colmap`. The archive is about 415 MB; installed binaries and GPU dependencies are local runtime prerequisites, excluded from Git, source archives and Docker contexts. No system PATH change is made. Supply FFmpeg with `--ffmpeg` or `FFMPEG_PATH` as described in [web setup](docs/web/WEB_SETUP.md). Build `frontend` for port 8000, or use the Vite development server as usual.

Discovery order: explicit `COLMAP_EXECUTABLE`, then `colmap` on PATH, then project-local `.tools/colmap/bin/colmap.exe` on Windows. An explicitly configured invalid executable is not replaced with another installation. The Python package and executable must both be version 4.2.1; the executable help must report CUDA and the NVIDIA driver must enumerate a usable device. CUDA-enabled Python installations keep the existing Python PatchMatch path.

`GET /api/health` reports `dense_reconstruction`, `dense_backend`, `dense_unavailable_reason` and `reconstruction_mode`. Holo displays readiness before upload and offers **Automatic**, **Dense room reconstruction + ceiling estimate**, and **Quick sparse preview**. Automatic respects server mode; in `auto` it selects dense when available. Explicit dense upload is rejected before creating a job when unavailable. Required dense failure never publishes sparse success.

## Processing and verification

The native worker uses the same policy, supplied K/poses, accepted-track neighbors, 960-pixel derived grid and CUDA stereo settings as the Python backend. CPU PyCOLMAP undistorts images and checks the model against source cameras. The executable runs with argument lists, without shell evaluation. Its SHA-256 and invocation type are saved in `backend.json`; the unchanged independent dense audit checks camera grids, poses, depth maps, multi-view consistency and cloud regeneration. Captured LiDAR, grounding dimensions and the supplied measured ceiling do not enter geometry.

After stereo and audit, the existing surface/room publisher estimates a supported floor, rough rectangular wall envelope and a provisional ceiling height where observations support it. Height can remain unavailable when upper-room coverage is insufficient. Dense geometry is not a guarantee of a verified ceiling plane or calibrated dimensions.

Jobs remain isolated and atomically published. Dense worker timeout terminates the entire Windows worker/CLI process tree. A failed later stage retains verified inputs for a separate retry; previous results remain available. Holo reports geometry quality, approximate dimensions and provisional ceiling height in both the capture result and reconstruction workspace. Catalog-refresh failures retain the loaded view and clear when the connection recovers.

## Verification record

**Known floor-plan regression:** native dense execution completed, but the new inferred rectangle is 4.539 Ã— 4.055 m versus the earlier approximately 3.327 Ã— 3.851 m result. The 2.551 m ceiling is provisional. This state is being preserved as the user-requested error baseline; the fix is deferred. [Exact results, reproduction and next investigation](NATIVE_DENSE_REGRESSION.md).

The development machine's CPU PyCOLMAP reported `has_cuda=False` despite an RTX 4060. This explains the previous sparse-only native behavior. The official archive checksum was verified as `e9c5cbd84c2ea986d2e970a2473fc2d2e6b34a2cdcf5d3df2765c319a63af881`; native discovery then reported `colmap_executable` available. End-to-end run results are recorded in [current progress](../context/progress.md).
