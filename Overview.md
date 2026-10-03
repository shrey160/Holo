# Prototype 2: ingestion first

Created: 2026-10-03 (Asia/Calcutta). State: context reviewed; ingestion definition is next. No new ingestion implementation or reconstruction trial has run.

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

These are context-derived requirements/questions, not a frozen schema or executed pipeline. Preserve raw captures and prototype-1 evidence. Define ingestion before selecting the next reconstruction candidate.
