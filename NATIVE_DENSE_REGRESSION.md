# Native dense reconstruction: error baseline

Status: **OPEN — documented baseline; geometry fix deferred by user**. Recorded 2026-10-04. The user requested this state be committed before work on the fix. This document separates successful native execution from the unresolved room-plan regression.

## What changed

The previous native Windows environment had an NVIDIA GPU but CPU-only PyCOLMAP (`has_cuda=False`). Automatic reconstruction therefore returned a sparse preview without a ceiling estimate. Holo now supports the official COLMAP 4.2.1 Windows CUDA executable alongside CPU Python bindings. A real HTTP upload completed ingestion, preprocessing, fixed-camera sparse reconstruction, dense RGB stereo, surface extraction, room estimation and publication without Docker. [Native setup and ownership](NATIVE_DENSE.md).

Frontend changes add backend readiness and unavailable reasons, an Automatic/Dense/Preview selector, grouped processing progress, quality/dimension/ceiling summaries, dense-versus-sparse result labels, selected-result URL updates, and separate catalog refresh errors. LiDAR messaging now distinguishes implemented CLI ingestion from planned app upload. Persisted stage history applies to workers started with the updated runner; the measured run began before that final presentation change. Its geometry result is retained unchanged.

## Observed regression

| Result | Earlier automatic Docker dense run | New native dense run |
|---|---|---|
| Job | `f02743deab6c46a3b93bf70dcb23ec16` | `ae77c443f85f449abad2c0598d4c7648` |
| Supported stereo views | 99 | 99 |
| Dense source points | 846,791 | 848,220 |
| Displayed points | 120,000 | 120,000 |
| Rough room dimensions | approximately 3.327 × 3.851 m | **4.539 × 4.055 m** |
| Rough area | approximately 12.8 m² | **18.405 m²** |
| Provisional ceiling | approximately 2.566 m | **2.551 m** |
| Execution status | Completed | `SUCCEEDED`, `DENSE_WITH_FINDINGS` |

The new outline is substantially larger than the earlier estimate for the same room. Compare side lengths without assuming the two estimators retained the same axis ordering. Neither result is independently calibrated ground truth. The earlier values come from preserved P2AUTO-002 records; that run was not repeated during this native test. The native ceiling remains a provisional upper envelope, not a verified ceiling plane: near-estimate support covers about 6.1% of the inferred room area. The separate user-reported ~2.6 m measurement was not used.

**Known issue:** dense execution and source/geometry integrity pass, but the inferred rectangular floor plan regresses. `SUCCEEDED` describes completion of the technical pipeline; it is not architectural or dimensional acceptance. No regression fix, forced 3 × 4 m dimensions, source scaling, pose refinement or measurement prior was applied before this snapshot.

## Reproduction and evidence

1. Follow [native dense setup](NATIVE_DENSE.md), with FFmpeg and the built frontend available.
2. Start Holo from `proto-2` using `web` + `reconstruct` extras, native CUDA executable discovery and `RECONSTRUCTION_MODE=auto`.
3. In Input & validation, upload `../test_data/iphn-17/zips/single_room.zip`, enable automatic reconstruction and select **Dense room reconstruction + ceiling estimate**. The recorded run explicitly requested `dense`; unavailable or failed dense cannot silently downgrade.
4. Inspect the resulting floor plan and ceiling summary. Each replay creates a new job; exact point counts and plane fits can vary across backend/platform execution.

Retained local result: [native error baseline in Holo](http://localhost:8000/?reconstruction=capture-ae77c443f85f449abad2c0598d4c7648#reconstruction). The local server uses `outputs/web-data-native`; Docker remained stopped. The source ZIP, raw files, intermediate dense/surface bundles, portable viewer and previous captures remain on disk. Git excludes raw captures, generated clouds/depth maps, Python environments and downloaded CUDA binaries.

Small reviewable artifacts are committed separately:

- [Frozen evidence JSON](docs/regressions/native-dense-2026-10-04/evidence.json): exact measurements, runtime/provenance, source and artifact hashes, comparison provenance and validation boundaries.
- [Frozen rough floor plan SVG](docs/regressions/native-dense-2026-10-04/rough-room.svg): the actual wider output, retained without alteration.
- [Evidence directory guide](docs/regressions/native-dense-2026-10-04/README.md): preservation and comparison rules.

The run completed in **907.7 seconds** (about 15.1 minutes); native stereo took **548.8 seconds**. It used 106 prepared views, selected 100 for sparse reconstruction and retained 99 for stereo, excluding unsupported rank 1755. Ingestion verified 1,756 frames and preprocessing verified exact source geometry. No captured LiDAR, grounding size/photo, user ceiling reference or human furniture annotations entered automatic geometry.

## Verification boundaries

- Final Windows regression suite: **185 tests passed**, no failures or skips; Ruff check/format passed. Tests establish behavior and integrity, not floor-plan accuracy.
- TypeScript and Vite build passed; the final broad Prettier format check passed after documentation formatting.
- uv lock validation and portable wheel/source build passed. Archive contents include the native runtime module, installer and setup documentation; local runtime binaries, caches and outputs were excluded.
- The downloaded official archive matched its release SHA-256. Runtime admission checked pinned version, CUDA build and a usable device. Backend executable identity is recorded in the evidence.
- The native pipeline's dense/surface/viewer publication audits passed, and 45 protected historical viewer/history files remained unchanged.
- Frontend readiness, quality selection and processing states were inspected in Holo. Further frontend acceptance and the corrected-plan comparison remain part of the later fix.

This commit checkpoints the accumulated prototype implementation since `e6e6ba9`, including the earlier reconstruction/viewer and modality work. It is an **error baseline**, not a claim that the known room-plan issue is resolved. No push is requested.

## Next investigation, after this commit

Preserve this run and its committed evidence. First compare native versus earlier output at sparse support, dense geometry, selected floor frame, candidate wall orientations and final footprint extent selection. Wall orientation, furniture/connector contamination, outliers and plane-selection sensitivity are **hypotheses**, not established causes. Identify the stage introducing the wider rectangle before changing it.

Prefer a separate, audited CPU re-publication from the retained dense/surface evidence when that stage is sufficient; rerun stereo only if the diagnosis warrants it. Save a new result and compare both outlines, ceiling estimates, source hashes and plan-to-3D orientation. Add a meaningful regression check for the diagnosed behavior, keeping room measurements out of fitting unless explicitly disclosed. Physical accuracy, object localization and multi-room stitching remain unresolved. Gaussian work remains deferred.
