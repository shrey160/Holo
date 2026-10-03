# iOS ingestion plan

Date: 2026-10-03 (Asia/Calcutta). Original planning task P2P-001; implementation/verification task P2I-001. State: Sensor Recorder 1.5/build 5 assisted-RGB ingestion implemented and verified on both supplied captures; other adapter proposals below remain future work. [Commands](README.md), [results](INGESTION_RESULTS.md), [capture protocol](capture.md). Initial repository commit: `36233d0`; no additional commit yet.

Current P2R-001 follow-up: source is now an installed modular package with an independent uv environment, lockfile and seventeen checks. [Architecture](ARCHITECTURE.md) and [refactor evidence](REFACTOR_RESULTS.md) supersede old script/environment instructions; original contract/records remain unchanged.

User follow-up: installed Sensor Recorder Pro on the base iPhone 17 without LiDAR and supplied single/double-room captures under `test_data/iphn-17`. P2D-001 inspected their export contract. P2I-001 subsequently ingested and replay-verified both recordings: 1,756/3,949 RGB/K/pose records and all sensor rows preserved, thirteen checks passed. User declared a 0.210×0.297 m opening reference; hash-bound annotations preserve it without localization or scale correction. Preprocessing/reconstruction remain NOT_RUN.

## Goal and boundary

Turn an untouched iOS export into a versioned, inspectable `CanonicalCapture` that reconstruction can consume without understanding the capture app. End ingestion after decoding/indexing, normalization, association and validation. Camera estimation/refinement, drift correction, frame selection for a model, geometry, splatting and property outputs are downstream stages.

The attached other-chat note contributes the adapter/common-capture separation, optional poses/depth and independently timestamped inertial streams. It is mostly Android advice, not evidence of an installed iOS app or its export schema. Android adapter implementation is deferred; optional capabilities provide enough extension room now.

## Capture paths and priority

| Path | Inputs | Initial use | Missing-input behavior |
|---|---|---|---|
| Sensor Recorder Pro 1.5/build 5, ARKit mode | `wide.mp4`, `arkit_pose.csv`, `meta.json`, independent IMU and fused device motion | First implementation target; both fresh exports inspected | Parse verified headers/comments and metadata declarations; physically unvalidated associations remain labelled |
| Existing Stray-like sessions | RGB, odometry/per-frame K, IMU, optional depth/confidence | Available development fixtures; first executable adapter if a fresh Sensor Recorder export is unavailable | Version-specific correspondence and conventions; retain unverified provenance |
| Native Camera video | Original MOV/MP4 plus embedded metadata | Required ordinary-video path | Poses/IMU generally absent; calibration unavailable unless actual supported metadata exists |
| Native Camera photos | Room folders with 2–8 real stills per room | Required photo path, after the temporal adapter | No fabricated timeline, pose, room adjacency or metric scale |
| LiDAR-capable iOS capture | RGB, calibration, trajectory and measured-depth records | Separate profile using the same contract | Validate actual device/export; base phone does not supply rear LiDAR |

Recommendation: begin with one rear wide camera and one uninterrupted session; avoid multi-camera fusion until camera-specific calibration, clocks and extrinsics are verified. Keep the ordinary-video and photo paths in the interface even while the assisted path is the first implementation target. Current supplied video frames cannot establish a genuine photo capture benchmark.

Initial public-source review did not establish the ARKit export layout; the supplied local 1.5/build 5 captures now resolve the parser layout and declared semantics. Support this observed version explicitly rather than assuming all releases match. Its listed free recording limit is two minutes; both supplied recordings fit that limit, but evaluate it against a longer continuous multi-room walkthrough before freezing the final capture protocol. [App listing](https://apps.apple.com/us/app/sensor-recorder-pro/id6782758613).

## Refinements from the actual exports

- `arkit_pose.csv` is both the RGB index and per-frame calibration/trajectory table; skip/preserve leading comment lines. No separate `wide_info.csv` is present.
- Decoded frame counts match pose rows exactly: 1,756 single-room and 3,949 double-room. Use verified `i -> i` association and native presentation timestamps; the old Stray initial-discard rule does not apply.
- Metadata declares camera-to-world optical poses, metre translations and w/x/y/z quaternions. No extra ARKit basis flip is required. Keep native pixels; derived orientation changes still need matched calibration/camera transforms.
- Independent acceleration is already m/s² and gyro rad/s. Do not apply g conversion again. Prefer independent streams over gyro-keyed combined IMU rows.
- Preserve initial limited tracking (eight double-room frames), IMU start offsets, changing intrinsics and actual per-frame exposure. Do not extrapolate early IMU.
- Each recording skips one `record_slot` number while frame/time continuity is preserved. This is not an observed dropped image.
- Use effective streams and ARKit mode over inactive Standard-mode settings that remain in the metadata. Missing depth is expected; unknown distortion/IMU extrinsics prevent an unqualified VIO-ready claim.

The [inspection report](../context/references/research/iphn-17-inspection.md) distinguishes observed file/clock integrity from physical synchronization, geometry and accuracy, which remain unvalidated.

## Pipeline stages

1. **Discover and fingerprint.** Accept a session folder initially; controlled archive import can follow. Identify adapter/version from metadata and verified headers, never folder name alone. Inventory source assets, sizes and SHA-256 hashes. Preserve original files and comments, disabled streams and exporter errors. Reject ambiguous sessions/camera choice rather than combining them.
2. **Parse each stream.** Read metadata and independent camera/accelerometer/gyro streams. Distinguish source device-motion attitude/gravity from raw IMU and from camera trajectory. Retain original IDs, row numbers, timestamp values/precision and units. Unknown fields remain available in source metadata; unknown required semantics prevent the relevant assisted profile from being ready.
3. **Decode and index all RGB observations.** Use FFprobe/FFmpeg with explicit orientation behavior. Decode in presentation order and retain rational media PTS/timebase, decoded rank, original size and packet/discard evidence. Probe alone does not prove full decodability. Do not generate `frame_number / fps` times or apply a model's temporal subsampling during ingestion.
4. **Associate clocks and frames.** Establish supported media-to-sensor correspondence, record every unmatched observation, and validate count/order/timing evidence. Output one capture-relative timeline where a common clock is established; preserve each native clock regardless. A good fit supports correspondence, not proof of physical synchronization.
5. **Normalize documented semantics.** Convert known units once; retain source values. Represent per-frame calibration and verified camera poses in declared conventions. Keep source image geometry as the default canonical grid; optional upright previews get explicit derived transforms.
6. **Validate and publish.** Produce machine-readable findings and a compact human report, capability/readiness records and reproducibility metadata. Build in a fresh temporary output and publish only after structural validation. Failed runs retain diagnostic reports, but are never advertised as ready. A rerun uses a new output or a verified content-addressed cache, never silently overwrites a prior capture.

## Proposed canonical bundle

```text
capture/
  manifest.json
  sources.json
  cameras.json
  clocks.json
  frames.csv
  calibration.jsonl
  imu/
    accelerometer.csv
    gyroscope.csv
    device_motion.csv       # optional, distinguished from raw IMU
  trajectory/
    source_poses.jsonl      # optional, supplied trajectory only
  depth/
    index.csv              # optional, source assets referenced
  validation/
    report.json
    summary.md
  previews/                # optional derived assets
```

This is an internal contract, not the missing official assignment JSON schema. Missing optional files are declared in the manifest; empty identity trajectories must not stand in for unavailable poses.

| Record | Required meaning |
|---|---|
| Manifest | Schema/adapter version, capture identity, platform/app/device/mode when known, source fingerprint, configuration/tool versions and capabilities |
| Source asset | Stable asset ID, relative locator plus configurable raw root, media type, bytes/hash, source stream and permitted usage; default bundle references raw data without copying it |
| Frame | Capture-scoped ID, camera ID, source frame/row ID, decoded rank or null, native PTS, sensor timestamp or null, relative time or null, calibration/pose links, decode/match status |
| Calibration | K, associated image dimensions, pixel convention, source and validity; distortion model/coefficients or explicitly unknown |
| IMU sample | Original time/value/unit/frame, canonical time/value when conversion is supported, source row and stream semantics including gravity treatment |
| Pose | Associated frame/time, segment ID, source transform and verified canonical transform, units, source/tracking state and conversion provenance |
| Depth observation | Own time/frame association, raw asset, units/invalid encoding, calibration/grid, confidence link if available and registration evidence |
| Validation finding | Stable code, severity, affected stream/frame range, measured evidence, policy/threshold provenance and affected readiness profiles |

Every stream has an availability state such as `AVAILABLE`, `MISSING`, `DISABLED`, `INVALID` or `UNVERIFIED`. Separately record evidence as source claim, source-verified semantics, local structural validation or independent physical validation. Presence never implies calibration or synchronization is verified.

## Time and frame association

Use the first matched primary RGB observation as relative origin for temporal captures; preserve pre-roll IMU with negative relative times. Never zero each stream independently. Native sensor seconds remain seconds with preserved decimal precision; converting to integer nanoseconds must not suggest extra source precision. UTC remains provenance, not the default fusion clock. Unknown clock relationships remain unknown. Still photos can have EXIF time but do not acquire a synthetic video timeline.

Sensor Recorder documentation identifies `sensor_sec` for alignment and `utc_sec` for external correlation. [Maintainer README](https://github.com/ydsf16/ios_sensor_recorder#time-model). The inspected exporter exposes camera indices/recording slots and separate IMU streams; its combined IMU rows attach the latest accelerometer observation to a gyro sample. Prefer independent streams, retaining both times when a combined export is the only source. It already converts acceleration to m/s². [Exporter source](https://github.com/ydsf16/ios_sensor_recorder/blob/main/SensorRecorder/ViewController.swift).

Plan to validate frame counts and metadata indices, match source timestamps against decoded media, and preserve excluded/failed writer observations. Equal counts alone do not prove alignment. Permit an offset or affine clock relationship only under a supported adapter rule with residuals and unmatched counts. Do not optimize a clock offset against reconstruction quality.

For the existing Stray fixture, preserve its documented initial-discard exception and test it explicitly. Do not reuse the `i -> i+1` mapping for Sensor Recorder, native video or other Stray versions. If correspondence is ambiguous, mark the sensor associations unavailable and fail assisted readiness; a separately requested RGB-only profile may remain usable.

## Coordinates, images and units

Canonical camera coordinates: optical x right, y down, z forward; poses are `world_from_camera` acting on column vectors, metres, with matrix serialization order declared. Preserve the source world within each verified continuous tracking segment, with an explicit transform if a downstream algorithm requests another origin. Do not normalize each room independently into the same world.

For an exporter proven to store raw ARKit camera poses, plan one camera-basis conversion; for an exporter already storing optical poses, apply none. Matrix direction, storage order, quaternion order and export orientation require source/export verification before enabling conversion. The Stray adapter's existing convention is evidence for that exporter, not Sensor Recorder. Preserve source poses; suspicious jumps become findings/segment boundaries only under stated evidence, not a silently corrected trajectory.

Each K belongs to a named camera and exact pixel grid. Apple documents that captured image dimensions refer to native sensor orientation. [Image resolution](https://developer.apple.com/documentation/arkit/arcamera/imageresolution?language=objc). Keep pixel transforms and camera-basis transforms separate; derived upright/resize/crop operations must update calibration and camera orientation consistently. Unknown distortion is not zero distortion. Device IMU axes stay intact; unknown camera-to-IMU extrinsics prevent a claim that the dataset is ready for tightly coupled VIO.

Use explicit exporter units over numeric heuristics. Apple Core Motion acceleration is measured in g, but an app can convert it before export. [Apple acceleration definition](https://developer.apple.com/documentation/coremotion/cmacceleration?language=objc). Sanity checks can flag conflicts; they must not silently choose units. Likewise identify measured depth, filtering/smoothing, optical-z versus range semantics and confidence encoding per adapter; do not treat depth resolution or timestamps as proof of RGB registration.

## Validation and input profiles

Structural failures: unreadable required RGB, unsupported required schema, duplicate/conflicting IDs, malformed/nonfinite required fields, invalid transforms, or unresolvable frame-to-metadata association. Fail the affected profile with a diagnostic record. Quality findings: blur/exposure, interval gaps, limited stream overlap, tracking limitations, pose jumps and incomplete metadata. Retain observations and publish statistics; any exclusion belongs to a named downstream selection policy.

Proposed timing diagnostics: counts, durations, interval median/p95/max, actual rate, duplicate/reversed times, stream start/end overlap and clock-fit residuals. Irregular intervals indicate gaps; exact dropped-frame counts require exporter IDs/slots. Thresholds are adapter/profile policies to freeze before implementation trials, not measurement-accuracy gates.

Publish readiness separately for RGB, calibrated posed RGB, gravity guidance, raw-IMU VIO and RGB-D. Missing IMU does not invalidate ordinary video; unknown extrinsics can make VIO unavailable while posed RGB remains available. A schema-valid capture can still be physically unvalidated.

Downstream readers receive a profile-specific allowlist: `photos`, `video_rgb`, `ios_assisted_rgb`, or `lidar_rgbd`. The main assisted-RGB reader exposes RGB/calibration/poses/IMU only. Measured depth/confidence and independent references stay in separate namespaces and are admitted only by explicit RGB-D/evaluation readers. Logs declare assistance actually consumed. Capture-time ARKit poses remain priors; ingestion does not satisfy the assignment's drift-correction requirement.

## Implementation sequence and completion checks

P2I-001 completed the contract foundation, first Sensor Recorder adapter, thirteen boundary/geometry/clock checks and full real-data plus deterministic replay verification. The current CLI is `uv run --locked cozmo-ingest --source <session> --annotations <optional-file> --output <fresh-folder>` after `uv sync --locked`. It admits the observed Sensor Recorder ARKit version only, so no adapter/profile switch is exposed yet. Source declarations for a user-provided scale prior live separately from raw files. `CaptureReader` provides RGB/assisted/evaluation role boundaries; these are API boundaries, not an OS sandbox. Other format adapters and physical calibration checks below remain pending design work.

1. **Export reconnaissance (DONE structurally):** P2D-001 inspected both installed Sensor Recorder captures, established version/headers and declared conventions, and checked full decoding, clock correspondence and archive integrity. Physical convention/extrinsic/timing checks remain open; use Sensor Recorder as the first adapter and retain Stray as a later compatibility/control adapter.
2. **Contract foundation:** freeze schema/profile/error records, pure parsing/normalization boundaries and fresh-output CLI behavior. Use Python/FFmpeg on Windows; no model dependency is needed for ingestion.
3. **First adapter:** implement one verified iOS format, decode/index all frames, retain raw asynchronous IMU and validate calibration/trajectory associations. Proposed CLI: `ingest --source <session> --adapter <verified-format> --profile ios_assisted_rgb --output <fresh-folder>`; this is not an available command yet.
4. **Verification:** analytic checks for unit conversion exactly once, shared-clock pre-roll, matched/unmatched frames, ray invariance under orientation/resize, pose direction, quaternion/matrix serialization and tracking resets. Include missing pose/K/IMU and schema/clock failure cases, and a reader check proving assisted RGB cannot access depth/reference assets.
5. **Real-fixture review:** short Stray session, floor-only discontinuity stress case, ceiling-inclusive long session and a fresh Sensor Recorder export when available. Compare all source hashes before/after; inspect overlay/reprojection evidence and frame-index samples around gaps/jumps. Repeated ingestion with the same input/configuration must produce the same associations and content, aside from explicitly separated runtime metadata.
6. **Extend iOS coverage:** native ordinary video, actual per-room photo folders and verified Pro-device depth exports. Android adapter and multi-camera fusion follow later without changing the downstream contract.

Done means a documented, reproducible ingestion command with verified associations for supported exports, explicit failures/readiness for unsupported cases, unchanged raw data, and portable source locators. P2I-001 achieved this bounded result for both Sensor Recorder captures. Next is preprocessing when requested: view quality/orientation, tracking-aware selection and reference-object corner validation. Physical calibration/synchronization, geometry accuracy, other input tiers and measurement benchmarks remain separate unfinished work.
