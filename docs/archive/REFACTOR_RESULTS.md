# Modular ingestion and uv verification

2026-10-03 (Asia/Calcutta), P2R-001. The original verified ingestion has been reorganized into the installed `cozmo_ingestion` package. [Architecture](../architecture/ARCHITECTURE.md) describes component ownership and extension points; [README](../../README.md) contains portable setup/run instructions.

## Changes

- `IngestionPipeline` coordinates injected source/video interfaces and a bundle writer.
- Typed data objects separate requests, parsed sources, media inspection, normalized observations, canonical content and execution metadata.
- Format/schema parsing, clocks, geometry, annotations, camera/sensor normalization, storage, reader access and verification have dedicated modules.
- A transaction owns fresh staging, failure diagnostics and final publication. Stateless numerical transformations remain functions.
- `pyproject.toml`, `uv.lock` and `.python-version` configure an independent Python 3.12 environment. CLI commands are `cozmo-ingest` and `cozmo-verify`. The root scripts are compatibility wrappers.
- Tests are grouped by behavior; Ruff provides formatting and lint checks. Runtime Python dependencies remain empty; FFmpeg/FFprobe are explicit external prerequisites.

## Observed validation

Windows, uv 0.12.1, Python 3.12.14, FFmpeg 8.1.2. The new project uses its own `.venv`, with no runtime dependency on prototype-1. Ruff 0.16.10 is recorded in the lockfile. `uv sync --locked --offline` passed after initial dependency acquisition.

**17 tests passed**, both in the editable project environment and an isolated environment installed from the built wheel. These include the original 13 geometry/clock/preservation/access checks plus reusable pipeline state, failed storage publication, moved-bundle rebasing and policy validation. Lint and format checks passed.

| Capture | Frames/K/poses verified | Sensor records/source hashes | Canonical hashes versus original | Replay |
|---|---:|---|---|---|
| Single room | 1,756 each | All preserved | All 16 identical | Identical |
| Double room | 3,949 each | All preserved | All 16 identical | Identical |

Complete FFprobe/FFmpeg ingestion ran twice per recording through the modular package. Warm initial pipeline times were about 3.95 s and 8.52 s; these are local observations, not clean-machine benchmarks. Original captures and previous generated bundles were not overwritten.

Baseline and current manifests differ only in `pipeline_source_sha256`: it now fingerprints every package Python module with normalized source line endings rather than the old single script. Current package fingerprint: `72f2f3410dfe5f07a342485fc982c6684485c43dd66a9323a7a4b47e4703c7e6`. Older bundles remain readable and were reverified.

Local evidence: [regression ledger](../../outputs/refactor-validation.json), [single manifest](../../outputs/single-room-modular-v1/manifest.json), [double manifest](../../outputs/double-room-modular-v1/manifest.json). Generated evidence is ignored and is not bundled into the submission archive; the commands in README reproduce verification when the recordings are supplied separately.

## Packaging boundary

`uv build --offline` produced a platform-independent Python wheel and source archive. The wheel was installed with no dependencies into a separate uv-created environment; isolated Python imports resolved to that environment's `site-packages`, and its package fingerprint matched the source package. Its installed CLI processed the real single-room recording and verified equality with the modular run.

Archive membership checks confirmed that the source archive includes code, tests, configuration, lockfile, declarations and documentation while excluding videos, generated outputs, virtual environments and caches. The extracted source archive independently completed `uv sync --locked --offline` with an existing tool cache and passed all seventeen tests. Imports resolved to that extracted project's own installed source. The wheel contains the package and entry points; it does not need the source checkout on its import path.

This validates packaging/isolated installation on the current Windows host. A different OS, Python 3.13/3.14, automatic Python download and a fully uncached clean machine have not been tested. FFmpeg/FFprobe must still be installed independently. Physical calibration/synchronization, dimensional accuracy, preprocessing, object localization, scale correction and reconstruction retain their previous unverified/NOT_RUN status. No additional commit or publication was performed.
