# Ingestion verification results

2026-10-03 (Asia/Calcutta), P2I-001. Supported boundary: Sensor Recorder Pro 1.5/build 5 ARKit on the supplied base-iPhone 17 single/double-room exports. Ingestion verified; preprocessing, reference-object localization, scale estimation, reconstruction and independent metric validation remain NOT_RUN.

This is the initial implementation's historical evidence. The current modular package/uv environment preserves all sixteen content hashes per recording; see [refactor verification](REFACTOR_RESULTS.md) for the current code layout and seventeen-test run. Historical source fingerprints below refer to the original monolithic script.

## Observed executions

Windows, Python 3.12 via the existing prototype-1 environment, existing FFmpeg/FFprobe; standard-library ingestion. No installation, model, GPU or network processing. Source fingerprint for ingestion code in all four manifests: `a2aa25e57d3e27520f28b83d451119f9c35201f4140c6531b9b99e8a3ce72280`. The verification utility is recorded separately in the [validation ledger](outputs/ingestion-validation.json).

| Capture | RGB/K/pose records | Full decode | Initial pipeline time | Replay time | Deterministic replay |
|---|---:|---|---:|---:|---|
| Single room | 1,756 each | Passed | 4.74 s | 4.02 s | Identical manifest/16 content hashes |
| Double room | 3,949 each | Passed | 8.87 s | 8.74 s | Identical manifest/16 content hashes |

Timings are warm local pipeline measurements before final publication/tool-version query, not cold setup or a clean-machine benchmark. Raw session asset hashes match the earlier inspection ledger and remain unchanged after all runs. Original ZIPs/source videos were not rewritten. Generated bundles/runtime evidence are Git-ignored, while source/docs/user scale declarations remain reviewable.

Artifacts: [single manifest](outputs/single-room-ingestion-v1/manifest.json), [single validation](outputs/single-room-ingestion-v1/validation/report.json), [double manifest](outputs/double-room-ingestion-v1/manifest.json), [double validation](outputs/double-room-ingestion-v1/validation/report.json), [single replay](outputs/single-room-ingestion-v1-replay/manifest.json), [double replay](outputs/double-room-ingestion-v1-replay/manifest.json).

## Checks and preserved findings

Thirteen analytic/boundary checks passed: known quaternion direction/translation; large-origin microsecond clock precision; no frame-count truncation/discard shift; clock mismatch/duplicate PTS rejection; unsupported axes/version rejection; path containment; source-bound scale declarations; unchanged acceleration units/pre-roll/limited observations; RGB/assisted reader reference exclusion; modified source/artifact detection; replay/no overwrite; failed diagnostics; and source mutation during ingestion. Synthetic video inspection is mocked in these tests; complete real FFprobe/FFmpeg processing was exercised separately by all four executions.

The verification utility reads every exported frame, K, pose and independent/combined sensor row against raw values, rechecks all source/artifact hashes and compares each replay. Runtime records are excluded from capture-content equality. Video PTS and camera clock correspondence are checked with rational ticks and a frozen 2 µs stored-clock tolerance; this is recorded association evidence, not measured physical sensor latency.

- Both sessions retain their single `record_slot` discontinuity without inventing an image gap.
- Double room retains all eight initial limited-tracking frames, the apparent high-speed pose step near 40.53 s and four initial exposures above the requested 5 ms cap. These are findings, not silently repaired geometry.
- Both sessions retain early camera observations without IMU coverage; no boundary extrapolation, synchronization resampling or position integration occurs.
- Images/K remain on the native 1920×1080 grid. Supplied world coordinates and optical poses are preserved; only quaternion serialization rounding is normalized when constructing proper rotation matrices, with raw quaternion strings retained.
- Camera-to-IMU extrinsics, distortion and physical RGB/IMU synchronization remain unverified. Raw-IMU VIO and RGB-D readiness are false.

## Grounding-object boundary

User declared a 21×29.7 cm object in the first few seconds of each video. The two [source declarations](capture_annotations/) bind that prior to the exact video hashes. In each bundle, the first-five-second candidate interval links **300 frames** to the declaration. This is a search window; object visibility, four corners, uncertainty and physical dimensions have not been verified by an algorithm. Localization and scale estimation remain `NOT_RUN`; `scale_applied` is false.

The prior is human scale assistance for future preprocessing, not a room-dimension evaluation reference. It is admitted explicitly via `--annotations` and never inferred from a filename or imposed on captures without declarations. [Capture guide](capture.md) explains the later manual-corner/calibrated-geometry approach and how to capture useful views. No learned detector, planar pose solver, global scale correction, floor inference or floor-plan model has run.

Next: preprocessing can preserve traceability while selecting usable views, managing native orientation/tracking limitations and manually validating A4 corner correspondences before considering automatic detection. Ingestion completion applies to this observed export version; other adapters and final all-tier accuracy remain unfinished.
