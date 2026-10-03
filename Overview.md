# Prototype 2: Holo ingestion milestone

Updated: 2026-10-03 (Asia/Calcutta). User authorized updating context and making a local milestone commit. Initial Git commit: `36233d0`; this milestone records the completed source, configuration, tests and documentation that followed it. Raw recordings, generated bundles/evidence, environments, dependencies and caches remain excluded. No push requested.

Holo validates complete Sensor Recorder Pro 1.5/build 5 ARKit exports through a modular Python core and CLI, an optional FastAPI service and React/TypeScript/Vite capture-guide/input tabs. Own uv environment/lockfile, Docker packaging, native development, bounded isolated jobs, persisted history and verified portable downloads are implemented. [Main/folder README navigation](README.md), [architecture](ARCHITECTURE.md), [Docker/native setup](WEB_SETUP.md), [verification](WEB_RESULTS.md), [capture guide](capture.md).

Latest accepted capture guidance: iPhone 15 and above is recommended; record one known-size object only in the first 3–5 seconds at the first entrance, then leave it there and continue through the rooms. Optional JPEG/PNG object photo input is independent of dimension declarations. Its original bytes, video binding and metadata hashes are retained, displayed after verification and included under `reference/` in downloads. Uploading a photo does not detect corners or estimate scale. Existing internal `cozmo_*` package/CLI names remain compatible.

Validation: 34 tests passed on Windows/Python 3.12.14 and Linux Docker; Python lint/format and frontend build/format passed. Both supplied captures preserve all source observations (1,756/3,949 RGB/K/pose records) and have identical native/container manifests and all sixteen canonical artifact hashes. Browser real-capture JPEG upload/download, source-value reverification and final-container persistence passed; native FFmpeg decoded a synthetic PNG. Historical bundles remain verifiable after documented LF/root-hint portability changes. [Current evidence](WEB_RESULTS.md) separates these observations from physical accuracy and historical packaging checks.

Next: preprocessing when requested, including native orientation, tracking/view quality and manual reference-corner validation before automatic scale estimation, then reconstruction. Android/other adapters, independent measurement accuracy, physical sensor registration/synchronization and final all-tier submission remain unfinished. No new reconstruction model selected or executed. Historical context below preserves provenance rather than a current unexecuted ingestion plan.

The user requested a separate `proto-2` and relevant-context review before defining its data ingestion pipeline. Current focus: RGB + calibration + supplied poses + IMU, excluding measured depth/confidence from reconstruction input. The final assignment still requires photos, ordinary video and LiDAR; assisted video retains its own label.

## Context carried forward

- [Project contract](../context/masterplan.md): whole-property geometry, damage/scope, intervals, independent benchmarks, drift correction and an unseen-space run. Deadline: 4 October 2026 at 7:00 pm IST. Official output schema and some scoring definitions are missing.
- [Dataset inspection](../context/references/research/test-data-inspection.md): three Stray-like development captures with RGB, odometry/per-frame intrinsics, IMU, depth and confidence. Prior integrity checks passed; independent dimensions and repeatability pairs are absent.
- [Sensor conventions](../context/references/protype_research/sensor-inputs.md): short capture has 1,714 decoded RGB frames versus 1,715 sensor records. Existing adapter verifies one initial discard, decoded-rank correspondence and an affine clock fit. This is not a universal mapping for other captures.
- [RGB preparation](../proto-1/run.py) and [sensor adapter](../proto-1/sensors.py): reusable hashes, native timestamps, matched pixel/camera transforms and input separation. Adapter is coupled to prototype-1 processing and its tested clockwise normalization/convention.
- [Sensor results](../proto-1/SENSOR_RESULTS.md) and [evaluation results](../proto-1/EVALUATION_RESULTS.md): assistance improves coherence; geometry remains incomplete. Assisted RGB sensor-proxy depth RMSE was 0.4240 m. Supplied-pose agreement is not independent dimensional accuracy.
- [Evaluator contract](../proto-1/EVALUATION.md): preserve source-frame identity, hashes, metric scale and camera/pixel transforms. Measured depth is a separately labelled evaluation proxy; using it for reconstruction is a distinct experiment.

## Questions for the ingestion definition

1. Which raw input layouts and capture modes should the first adapter support?
2. What model-independent capture/frame/IMU contract should reconstruction consume?
3. How should native IDs, presentation/sensor timestamps, omitted observations and alignment evidence be retained?
4. How should per-frame calibration, optical camera-to-world poses, units, world origin and rotation/resize/crop transforms be represented?
5. How should validation expose blur, missing data, coverage limits and pose discontinuities without silently repairing evidence?
6. How should ingestion be separated from reproducible view selection/model preprocessing, with evaluation references outside the assisted-RGB input path?

Per-frame intrinsics supersede the final-frame `camera_matrix.csv`. Reference exporter quaternions already use optical camera axes; do not apply a second ARKit flip for that convention. Existing IMU acceleration norms near one support raw g despite a conflicting format claim; current use is qualified gravity/gyro diagnostics, not position integration. Physical synchronization, RGB/depth registration, installed exporter identity and independent metric accuracy remain unverified. Two suspicious pose steps near frames 005199–005200 make the floor-only capture a useful future ingestion stress case.

These historical context-derived questions motivated the now-implemented ingestion contract. Preserve raw captures and prototype-1 evidence; use the current architecture/results for executed behavior before selecting the next reconstruction candidate.
