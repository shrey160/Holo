# Holo prototype handoff

Updated 2026-10-04. **Current boundary: native dense error baseline checkpoint; geometry fix not started.**

Read [the known regression and reproduction](NATIVE_DENSE_REGRESSION.md) first. Native Windows dense processing now works through official COLMAP CUDA alongside CPU PyCOLMAP; the real run produced 848,220 points, a provisional 2.551 m ceiling and a regressed 4.539 × 4.055 m room rectangle. The previous automatic Docker result was approximately 3.327 × 3.851 m / 2.566 m. These are uncalibrated estimates. The root cause is unresolved.

The user's latest instruction is to document and commit this state as the error baseline, then work on a fix in a subsequent step. Preserve the failing output and original source geometry; do not force expected dimensions. [Frozen evidence](docs/regressions/native-dense-2026-10-04/README.md).

Delivered capabilities: Holo capture guide, verified uploads/history/downloads, automatic ARKit video preprocessing and sparse/dense reconstruction, rough plans and interactive 3D; photo ingestion through CLI/Holo; supplied raw LiDAR ingestion through CLI. Photos stop after ingestion; LiDAR app upload remains planned and its conventions remain unverified. [Modalities](INPUT_MODALITIES_PLAN.md), [automatic workflow](AUTOMATIC_RECONSTRUCTION.md), [native setup](NATIVE_DENSE.md).

Gaussian appearance work is retained but deferred by user direction. Photo reconstruction/scale, LiDAR fusion, calibrated accuracy, automatic object localization and multi-room stitching remain unfinished. Current test evidence: 185 Windows tests passed, Ruff clean, TypeScript/Vite build passed. Passing tests and technical pipeline success do not certify the room outline.

The broader project memory is maintained at `../CONTEXT.md` and `../context/`; those files sit outside this prototype's Git repository. This local handoff and the regression evidence make the committed baseline self-contained.
