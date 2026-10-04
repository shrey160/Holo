# Provided dataset ingestion

2026-10-03, P2DATA-001. This extends Holo to the captures provided for the assignment under `test_data/drive_download`, separately from the user's Sensor Recorder recordings under `test_data/iphn-17`.

## Add a capture

Open **Input & validation** and choose one original archive from `../test_data/drive_download/zips/`:

- `single_room.zip`
- `single_scan_floor_only.zip`
- `single_scan_with_ceiling.zip`

Add a descriptive capture name and select **Validate capture**. ZIPs retain the complete nested session, including depth/confidence files. The same upload works in Docker and native development; no developer-specific path or dataset mount is built into the service. For CLI, select the extracted session directory, not its containing dataset folder:

```shell
uv run --locked cozmo-ingest --source ../test_data/drive_download/single_room/c00a170fe1 --output outputs/provided-single
uv run --locked cozmo-verify --capture outputs/provided-single --source ../test_data/drive_download/single_room/c00a170fe1
```

The other extracted sessions are `single_scan_floor_only/1a8384c3f6` and `single_scan_with_ceiling/c7d28f72c6`, relative to `../test_data/drive_download/`. Use a fresh output folder for each run. Supply `--ffmpeg` if media tools are absent from PATH. [Setup](../web/WEB_SETUP.md).

The A4 object declaration belongs to the user's recordings. These provided captures have no declared opening object or independent dimensions; leave optional reference dimensions/photo empty unless you have evidence for that exact capture.

## Source contract

The adapter requires `rgb.mp4`, `odometry.csv`, `imu.csv` and `camera_matrix.csv`, with the inspected exact headers and sequential odometry IDs. It selects per-frame intrinsics from odometry and checks that the legacy matrix matches the final frame. Present depth/confidence folders must have matching source IDs; files are retained and hash-checked without decoding or consuming their pixels in this ingestion stage.

This layout follows [Stray's format reference](https://raw.githubusercontent.com/strayrobots/scanner/main/docs/format.md). The inspected [odometry encoder](https://github.com/strayrobots/scanner/blob/ec3e1dc9d33f8df2289ede6a5c59f7991d1a6bbb/StrayScanner/Helpers/OdometryEncoder.swift) converts ARKit camera axes before exporting camera-to-world quaternions. The adapter preserves those optical poses with no additional flip or recentering. Installed exporter identity/version are unknown; conventions carry `FORMAT_REFERENCE_ASSUMED` evidence.

Raw acceleration is preserved without conversion. The [reference sensor encoder](https://github.com/strayrobots/scanner/blob/ec3e1dc9d33f8df2289ede6a5c59f7991d1a6bbb/StrayScanner/Helpers/DatasetEncoder.swift) writes CoreMotion values, conflicting with the documentation's acceleration-unit label. Units remain `UNRESOLVED`; the combined CSV timestamp does not recover separate sensor sample times. Read these records through `CaptureReader.records("native_imu")`; do not treat them as Sensor Recorder's independently timestamped SI streams. Tracking state, exposure and UTC are absent and stay unreported.

Each provided video normally decodes one fewer frame than its odometry stream. The adapter requires one negative-PTS discarded packet preceding decoded RGB, maps decoded rank `i` to odometry ID `i+1`, and validates an affine PTS/sensor-clock fit. Slope must be within 1% of one and maximum residual at most 10 ms. Count, discard, timestamp or fit failures reject the capture. Physical synchronization remains unverified; this is an audited association, not a clock or trajectory correction.

The first unmatched pose is retained in `trajectory/unassociated_source_poses.jsonl`, source metadata and the original hashed odometry file. Decoded RGB frame references, associated K/poses and every native IMU row are retained. No frame selection, rotation, resampling, scale correction or geometry processing runs.

`video_rgb` denies pose, IMU and measured-depth access. `ios_assisted_rgb` admits K/poses/native IMU and denies both depth and confidence. `evaluation` can explicitly read the retained depth/confidence assets, with provenance and hashes. RGB-D reconstruction readiness remains false.

## Verification

| Provided session | Decoded RGB / associated K / poses | Source odometry records | Native IMU rows | Maximum affine-clock residual |
|---|---:|---:|---:|---:|
| single_room | 1,714 | 1,715 | 3,689 | 0.030 ms |
| single_scan_floor_only | 5,250 | 5,251 | 11,397 | 0.122 ms |
| single_scan_with_ceiling | 9,744 | 9,745 | 21,339 | 0.361 ms |

All three passed Windows ingestion and Docker HTTP upload/ingestion, full FFmpeg video decode, source-value audits and asset hash checks. All three are stored as verified jobs in Holo history. Windows and Docker have equal source/pipeline identities and 12 identical canonical artifact hashes per session. The thirteenth artifact, `sources.json`, differs only because CLI and web storage use different raw-root hints; the raw asset identities remain equal (3,434 / 10,506 / 19,494 source files). The floor-only capture retains the two apparent pose-speed findings; no repair is applied. Seven new behavioral tests extend the suite to **41 passing tests on Windows and Linux Docker**, covering discard/clock failures, native values, deterministic replay, input-role boundaries, source tampering, mixed formats and nested/multi-session ZIPs. Frontend type/build and Python lint/format checks pass.

The browser accepted the original provided single-room ZIP, showed 1,714 frames and 13 verified artifacts, and downloaded a portable archive. ZIP CRC and extracted source-value verification passed, including retained depth/confidence assets. Completed earlier Sensor Recorder/photo jobs survived the Docker rebuild and remain compatible.

Local evidence is kept under ignored `outputs/supplied-data-evidence/`: `native-final-ledger.json`, `docker-ledger.json`, `cross-platform-validation.json`, `browser-download-verification.json` and `packaging-validation.json`. Wheel/source archives include the new modules/tests/guide and exclude raw/generated/private data; raw captures and these generated bundles are not included in source distributions. API results also retain verification evidence in the local Docker volume. Other exporters, physical registration/metric accuracy and measured-depth reconstruction remain unvalidated. [Architecture](../architecture/ARCHITECTURE.md), [main guide](../../README.md).
