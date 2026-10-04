# RGB, pose and IMU preprocessing

**Current automatic workflow (2026-10-04):** Holo automatic uploads proceed from verified preprocessing to bounded CPU sparse reconstruction and viewer publication. Manual preprocessing and existing prepared runs remain supported; quality findings are retained and do not certify geometry. [Automatic orchestration](../../AUTOMATIC_RECONSTRUCTION.md).


This stage prepares the user's inspected Sensor Recorder iOS captures for a reconstruction trial. It uses RGB, per-frame calibration, supplied ARKit poses and independent accelerometer/gyroscope streams. **LiDAR, confidence, grounding dimensions/photos and evaluation references are excluded.** Stray-style ingestion remains supported, but this first preprocessing version deliberately rejects that adapter because its sensor conventions and acceleration units remain unresolved.

Preprocessing writes a separate immutable derived bundle. It neither modifies the raw capture nor rewrites its ingestion bundle. ARKit metre translations remain the initial scale; physical measurement accuracy, camera/IMU extrinsics and physical timing alignment remain unverified. No new VIO, pose smoothing, drift correction, object detection, depth estimation, room segmentation or floorplan reconstruction runs.

## Run it

In Holo, open **Input & validation**, select a verified Sensor Recorder capture and click **Prepare reconstruction views**. A separate history entry runs through the existing bounded queue and isolated worker. Its result shows selected thumbnails, motion findings, supported/weak neighboring links and a downloadable report. The capture ZIP includes the original inputs and the derived preprocessing directory. Reference metadata/photos can remain archived for later use; they are not preprocessing inputs.

Native Python works independently of Docker and the web interface:

```powershell
uv sync --locked --extra preprocess
uv run --locked --extra preprocess cozmo-preprocess outputs/single-room-cli-v2 outputs/single-room-prepared --source ../test_data/iphn-17/single_room --ffmpeg C:/path/to/ffmpeg.exe
uv run --locked --extra preprocess cozmo-preprocess outputs/single-room-cli-v2 outputs/single-room-prepared --source ../test_data/iphn-17/single_room --verify-only
```

Supply an existing verified ingestion bundle and its unchanged source folder. If FFmpeg/FFprobe are on PATH, omit `--ffmpeg`. The same command works on Linux with POSIX paths. For native Holo, `uv sync --locked --extra web` installs the preprocessing dependencies too; existing [web setup commands](../web/WEB_SETUP.md) remain valid. Docker installs the same locked web dependencies and serves the compiled frontend.

Output must be fresh and separate from the source and ingestion bundle. Failed runs retain staging diagnostics and never publish a complete output. Retry creates a new run. `--candidate-fps 8` can investigate rapid/weak intervals at higher cost; the maximum admitted rate is 10 Hz. The configuration and package fingerprint are recorded for every run. Do not compare runs as if different sampling policies were identical.

## Processing contract

1. Use `CaptureReader(profile="ios_preprocessing")` to verify hashes and admit only allowed sources/artifacts. Hash checks may cover archived metadata for integrity; geometry never reads the reference annotation or image.
2. Decode the full native stream sequentially with FFmpeg, disabled autorotation and no frame-rate conversion. Associate decoded ranks with the ingestion index; count and grid changes fail. Sample one actual frame per 0.25-second bin at the default 4 Hz, plus the last observation.
3. Score candidate frames on grayscale analysis copies capped at 640 pixels wide. Record Laplacian variance, texture corners, clipping fractions, brightness and histogram changes. Quality score = 45% relative sharpness + 35% texture + 20% exposure. Relative sharpness uses the session's candidate p90; it is not a calibrated probability or cross-capture accuracy score.
4. Preserve start/end frames. Pick the best normal-tracking candidate per 0.375-second coverage bin and add candidates for 0.10 m translation, 10-degree rotation, tracking changes and context around apparent source-pose speeds above 3 m/s. The maximum-gap target is 0.75 seconds. Report gaps when candidate rate or capture timestamps cannot satisfy it. No doorway detector or room labels are inferred.
5. Index independent native IMU samples and expose actual sample ranges for each selected interval. No boundary extrapolation, resampling, acceleration integration or device-to-camera rotation is applied. Raw gyro magnitude above 1.5 rad/s in a Â±0.125-second neighborhood flags fast device rotation; this is a configurable diagnostic rather than a rejection rule. Fused device motion and magnetometer are deferred.
6. Match adjacent selected views with SIFT (up to 1,200 features), L2 nearest neighbors and a 0.75 ratio test, with unique target-feature support. RANSAC estimates a fundamental matrix and homography at a 3-native-pixel threshold. A supported visual link needs at least 20 inliers and an inlier ratio of at least 0.35. A homography can support a plane or pure rotation and does not establish triangulatable depth.
7. Add intervening 4-Hz candidates for weak links in one bounded recovery pass, then rematch. Retain unresolved links in the report. Translation under 2 cm marks a low-baseline link. Supplied-pose Sampson residuals are consistency diagnostics on image matches, not independent trajectory accuracy or a pose correction.
8. Export selected native-grid JPEGs (quality 95, lossy encoding), untouched per-frame K/poses and native sensor rows. There is no geometric rotation, crop, resize or undistortion of exported reconstruction images. Smaller images are presentation/analysis copies only; matched keypoint coordinates are mapped back to the native grid using pixel-center-aware scaling.
9. Recheck admitted source hashes, verify derived identities and publish atomically. The verifier checks all artifact hashes, image grids, exact frame/K/pose/native-IMU values, native sensor interval statistics, pair identities and input usage. This verifies the preparation contract; it does not prove room coverage, physical synchronization, geometry accuracy or a floorplan.

## Output

| Artifact | Purpose |
|---|---|
| `manifest.json` | Source video/ingestion identities, policy, tool versions, package fingerprint and artifact hashes |
| `views.jsonl` | Selected ranks/IDs, original timing, image/K/pose references, quality, motion and selection reasons |
| `images/*.jpg` | Native-grid selected reconstruction images |
| `thumbnails/*.jpg` | Small native-orientation candidate previews; excluded from reconstruction geometry |
| `candidates.jsonl` | Every sampled candidate, scores, flags and selection status |
| `calibration.jsonl`, `poses.jsonl` | Exact selected ingestion records; source axes/world and units preserved |
| `imu/*.csv`, `imu_intervals.jsonl` | Unchanged independent observations and traceable interval summaries |
| `pairs.jsonl` | Adjacent image-support, baseline and supplied-pose consistency diagnostics |
| `usage.json` | Admitted artifact/source access log |
| `report.json` | Counts, unresolved links, motion/coverage findings, input exclusions and review readiness |

`PREPARED_WITH_FINDINGS` describes successful preprocessing publication. `REVIEW_REQUIRED` is returned for unresolved image links, apparent pose-speed events, excessive temporal gaps or a sequence dominated by low-baseline links. Otherwise `READY_FOR_RECONSTRUCTION_TRIAL` permits an experiment, not an accuracy claim. `temporal_components` counts breaks in the adjacent-view chain; it is neither the number of rooms nor a global correspondence-graph component count.

## Modules and limits

The [package guide](../../src/cozmo_preprocessing/README.md) describes the application service and injected decoder. NumPy and headless OpenCV are optional for CLI-only ingestion; the web extra includes them. Lockfile resolves Python/OS-specific wheel hashes. Limits: 36,000 decoded frames, 2,400 sampled candidates, 8 million native pixels per frame, one web worker and the existing 600-second job deadline. Records/features remain in memory; candidate images use temporary staging storage. Long captures and mobile browsers remain unbenchmarked.

FFmpeg/OpenCV versions and platforms can change JPEG pixels, feature detections and threshold decisions. The implementation records tool/policy identities and keeps source observations exact; byte-identical derived images across platforms are not promised.

## Initial validation

Windows Python 3.12.14, FFmpeg 8.1.2, NumPy 2.5.3 and OpenCV 4.14.0; the final Windows/Linux suites have 53 passing tests including 12 new preprocessing/domain/HTTP tests. Real native runs verified:

| Capture | Original frames | Candidates | Selected views | Supported adjacent links | Weak links | Largest selected time gap |
|---|---:|---:|---:|---:|---:|---:|
| Single room | 1,756 | 118 | 106 | 98 | 7 | 0.5002 s |
| Double room | 3,949 | 265 | 240 | 209 | 30 | 0.5002 s |

Both need review; the double-room source's initial limited tracking and 3.60 m/s apparent pose step at 40.548 seconds remain recorded. Selected views retain exact source K/poses and native IMU rows. No source values, scale or trajectory were corrected.

Both real Docker runs were started through Holo's preparation button and passed the derived/source audits. Linux FFmpeg 5.1.9 produced the same selected ranks and counts as native FFmpeg 8.1.2. The downloaded double-room archive also has identical hashes for selected K/poses, accelerometer, gyro and interval summaries across platforms. This comparison does not require identical JPEG pixels or all floating-point image-quality scores.

Browser checks confirmed separate completed history entries, selected-view pagination, thumbnails and review/motion copy. The browser's 154,656,287-byte double-room ZIP passed CRC, re-extracted source/derived audits and byte-hash comparison of every raw file with the original recording. Gallery/thumbnail samples retain the doorway transition around 38.5â€“42.5 seconds in native orientation; this is a visual spot check, not proof of complete room coverage or a connected 3D reconstruction. [Validation ledger](../../outputs/preprocessing-evidence/validation.json), [result screenshot](../../outputs/holo-preprocessing.png). Physical accuracy remains unmeasured.

## Research references

- [COLMAP capture/tutorial guidance](https://colmap.github.io/tutorial.html): overlapping views, translated viewpoints, video downsampling and geometric verification.
- [OpenCV camera model](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html): K, world-to-camera projection and grid-dependent intrinsics. Our canonical stored poses remain camera-to-world and are inverted only for pair diagnostics.
- [OpenCV matching](https://docs.opencv.org/4.13.0/dc/dc3/tutorial_py_matcher.html): SIFT/L2 matching and nearest-neighbor ratio filtering.
- [FFmpeg options](https://ffmpeg.org/ffmpeg.html): native decoding, frame-rate mode and disabled autorotation.

Weak-link and doorway review is now complete: [findings](PREPROCESSING_REVIEW.md) include bounded temporal/revisit matching and resolution diagnostics without modifying these outputs. The [reconstruction plan](../reconstruction/RECONSTRUCTION_PLAN.md) led to the implemented fixed-pose sparse CLI: [native/Docker results and commands](../reconstruction/RECONSTRUCTION.md). Dense surfaces and floorplan extraction remain subsequent stages. Grounding-object algorithms and LiDAR remain deferred by the user's current decision.
