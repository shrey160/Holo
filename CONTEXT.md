# Holo prototype handoff

Updated 2026-10-04. **Current boundary: automatic dense floor-plan regression corrected and audited.**

Read [the correction and reproduction](NATIVE_FLOOR_PLAN_FIX.md) first. Automatic dense fitting previously used raw projected plane endpoints despite available height-persistence diagnostics. It now fits those supported source-aligned spans and fails visibly if they cannot support a room. Audited CPU republication of the unchanged 848,220-point native cloud gives approximately 3.147 × 3.706 m / 2.573 m ceiling, versus the failing 4.539 × 4.055 m / 2.551 m. These remain uncalibrated hypotheses; occluded wall ends can underestimate size.

The user authorized the fix after error baseline `d9723e2` was committed and pushed to `https://github.com/shrey160/Holo` on `main`. Corrected result `native-dense-floor-plan-fixed-v1` is separately published in native Holo; original job `ae77c443f85f449abad2c0598d4c7648`, failing viewer, cloud/colours/floor transform and historical results are preserved. No measured dimensions entered fitting. [Frozen baseline](docs/regressions/native-dense-2026-10-04/README.md), [correction evidence](docs/regressions/native-dense-2026-10-04/fix/README.md). Updated native server remains on port 8000; Docker and fresh GPU inference were not rerun for this correction.

Delivered capabilities: Holo capture guide, verified uploads/history/downloads, automatic ARKit video preprocessing and sparse/dense reconstruction, rough plans and interactive 3D; photo ingestion through CLI/Holo; supplied raw LiDAR ingestion through CLI. Photos stop after ingestion; LiDAR app upload remains planned and its conventions remain unverified. [Modalities](INPUT_MODALITIES_PLAN.md), [automatic workflow](AUTOMATIC_RECONSTRUCTION.md), [native setup](NATIVE_DENSE.md).

Gaussian appearance work is retained but deferred by user direction. Photo reconstruction/scale, LiDAR fusion, calibrated accuracy, automatic object localization and multi-room stitching remain unfinished. Current test evidence: 187 Windows tests passed, Ruff clean; no frontend source changed in the correction. Passing tests and technical pipeline success do not certify the room outline.

The broader project memory is maintained at `../CONTEXT.md` and `../context/`; those files sit outside this prototype's Git repository. This local handoff and the regression evidence make the committed baseline self-contained.
