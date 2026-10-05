# Holo prototype handoff

Branch policy, 2026-10-06: ongoing post-submission work belongs on `post-sub-improvements`.
Keep `main` as the submission snapshot at `020b6e5`; do not merge improvements into it
without explicit user direction. The new branch was created from that commit with all
existing tracked edits and untracked files preserved. Git records the submission tip
as 2026-10-04 18:57:24 +0530; the user confirmed 4 October around 7 pm.
The user authorized committing and pushing the pending work on this branch.
The checkpoint also preserves earlier example data, capture CLI and submission
documentation drafts; those drafts do not certify completion of all deliverables.

Latest work, 2026-10-06: [room-wise capture-route analysis](docs/reconstruction/ROOMWISE_PLAN.md).
Implemented provisional scanning stays/revisits without requiring corridor exits, local accepted-pixel
voxel associations, separate surface budgets and an automatic partial-evidence viewer. Cached native
two-room replay identifies R01 (10.505–35.511 s) and R02 (44.501–65.824 s); both still fail independent
wall-support completion. New viewer `two-room-route-review-20261006-v2` is open on native Holo port 8000.
No closed two-room plan, doorway detection, stitching, drift correction or new ceiling estimates.
Original failed job/sources/results preserved. 198 Windows tests pass with native process permissions;
Ruff/TypeScript/build pass; local replay matches published room-wise data. Docker/fresh stereo not rerun.
[Evidence](docs/regressions/roomwise-2026-10-06/README.md). Included in the post-submission branch checkpoint.

Latest test, 2026-10-05: [native two-room recording](docs/regressions/two-room-2026-10-05/README.md). Input/preprocessing/sparse/dense/surface stages ran; 82 stereo views and 468,728 dense points. Full job `6927cd39123049a492ae9e3c2165be63` failed the unchanged room-completion gate (`DENSE_ROOM_SUPPORT_INSUFFICIENT`). Separately audited partial viewer `two-room-dense-partial-20261005` is available in native Holo at port 8000, showing 120,000 points and open plan evidence. No closed two-room plan, dimensions or ceiling estimate; no multi-room segmentation. Original ZIP preserved; all eight partial viewer HTTP assets match hashes. This test is separate from the completed single-room fix below.

Updated 2026-10-04. **Current boundary: automatic dense floor-plan regression corrected and audited.**

Read [the correction and reproduction](NATIVE_FLOOR_PLAN_FIX.md) first. Automatic dense fitting previously used raw projected plane endpoints despite available height-persistence diagnostics. It now fits those supported source-aligned spans and fails visibly if they cannot support a room. Audited CPU republication of the unchanged 848,220-point native cloud gives approximately 3.147 × 3.706 m / 2.573 m ceiling, versus the failing 4.539 × 4.055 m / 2.551 m. These remain uncalibrated hypotheses; occluded wall ends can underestimate size.

The user authorized the fix after error baseline `d9723e2` was committed and pushed to `https://github.com/shrey160/Holo` on `main`. Corrected result `native-dense-floor-plan-fixed-v1` is separately published in native Holo; original job `ae77c443f85f449abad2c0598d4c7648`, failing viewer, cloud/colours/floor transform and historical results are preserved. No measured dimensions entered fitting. [Frozen baseline](docs/regressions/native-dense-2026-10-04/README.md), [correction evidence](docs/regressions/native-dense-2026-10-04/fix/README.md). Updated native server remains on port 8000; Docker and fresh GPU inference were not rerun for this correction.

Delivered capabilities: Holo capture guide, verified uploads/history/downloads, automatic ARKit video preprocessing and sparse/dense reconstruction, rough plans and interactive 3D; photo ingestion through CLI/Holo; supplied raw LiDAR ingestion through CLI. Photos stop after ingestion; LiDAR app upload remains planned and its conventions remain unverified. [Modalities](INPUT_MODALITIES_PLAN.md), [automatic workflow](AUTOMATIC_RECONSTRUCTION.md), [native setup](NATIVE_DENSE.md).

Gaussian appearance work is retained but deferred by user direction. Photo reconstruction/scale, LiDAR fusion, calibrated accuracy, automatic object localization and multi-room stitching remain unfinished. Current test evidence: 187 Windows tests passed, Ruff clean; no frontend source changed in the correction. Passing tests and technical pipeline success do not certify the room outline.

The broader project memory is maintained at `../CONTEXT.md` and `../context/`; those files sit outside this prototype's Git repository. This local handoff and the regression evidence make the committed baseline self-contained.
