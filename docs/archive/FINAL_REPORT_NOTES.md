# Final report notes

## Native dense compatibility and retained floor-plan regression

On 2026-10-04 the native Windows environment was found to have a usable NVIDIA GPU but CPU-only PyCOLMAP. Its sparse-only output was a backend capability limitation. An official, checksum-verified COLMAP 4.2.1 Windows CUDA executable now supplies stereo alongside the portable CPU Python environment, without Docker. The archive download is about 415 MB; setup cost and runtime prerequisites must be disclosed separately from inference time.

The real native automated run completed in about 907.7 seconds and produced 848,220 dense points, 120,000 displayed points and a provisional 2.551 m ceiling. However, the inferred floor plan expanded to 4.539 Ã— 4.055 m (18.405 mÂ²), compared with the preserved earlier approximately 3.327 Ã— 3.851 m automatic estimate. Integrity and 185 regression tests pass; dimensional/architectural acceptance does not follow from those checks. Root cause is unresolved. The user requested this be documented and committed as an error baseline before a later fix. Preserve the exact result and comparison rather than reporting only the successful native execution. [Evidence, reproduction and next investigation](../../NATIVE_DENSE_REGRESSION.md).

**Current automatic workflow (2026-10-04):** The initial CPU automation regressed room quality by replacing the richer dense pipeline with a sparse coverage envelope (3.70 Ã— 2.41 m, no ceiling estimate). The correction automates fixed-camera sparse tracks â†’ CUDA RGB stereo â†’ supported surfaces â†’ provisional floor/walls/ceiling â†’ plan/3D. CPU mode remains explicitly labelled preview; required dense failures remain visible. Opening RGB views remain eligible, while reference dimensions, measured ceiling and human furniture annotations are excluded. Applying the automatic estimator to preserved dense data yields 3.15 Ã— 4.10 m and 2.54 m high without forced values; fresh execution results are recorded in AUTOMATIC_RECONSTRUCTION.md. Multi-room segmentation and calibrated accuracy remain unresolved. Further Gaussian work remains deferred. [Architecture, experiments and limitations](../../AUTOMATIC_RECONSTRUCTION.md).


## Gaussian appearance experiment: further work deferred

On 2026-10-04 the user asked to stop Gaussian-splatting work and return to floorplan optimization because additional setup, downloads, resources and optimization would consume time. This is a project prioritization decision, not a claim that the existing trial failed to run.

A bounded trial had already completed: fixed source cameras/scale, 100,000 Gaussians, 90 appearance-training views and 10 photometric holdouts at 640Ã—360. The selected 10,000-step fit reached mean PSNR 21.94 dB and local SSIM 0.789 in 68.51 seconds on the RTX 4060 Laptop GPU. The initial dependency/image setup took approximately 40 minutes; this is distinct from training time. These timings are observations on this machine, not clean-machine guarantees. [Detailed implementation and results](../appearance/GAUSSIANS.md).

The rendered scene is available as a separate appearance artifact. Fine details remain soft; novel viewpoints can blur, tear or reveal gaps. Stereo initialization used all source views, including photometric holdouts. This is not an independent geometry benchmark or evidence of improved floorplan dimensions. Further downloads, model changes, tuning, densification and splatting-specific refinement are deferred. Existing artifacts are retained; no additional Gaussian work is scheduled.

The floorplan work continues using the existing RGB stereo geometry, source poses, intrinsics and reviewed structural evidence. Gaussian geometry is not an input to floorplan optimization.

## User-reported ceiling reference

On 2026-10-04 the user reported a measured ceiling height of **about 2.6 m**. Keep the approximate wording: no measurement method, uncertainty interval, exact location or capture-specific binding was supplied. This is an external reference for later ceiling-height comparison, not a recovered algorithm output.

Store reference measurements separately from reconstruction inputs. If a later experiment uses 2.6 m as a geometric prior or scale constraint, explicitly disclose that assistance and retain an unassisted comparison. No ceiling error, calibration success or scale correction has been established from this statement alone.


## User-requested complete rough plan

The user accepted errors and requested a complete single-room outline. A CPU rectangular hypothesis now gives about 3.2 Ã— 4.1 source-estimated m (about 13 mÂ²), an inferred entry and a separately displayed user ceiling reference of about 2.6 m. The full walls/corners and door width/swing are assumptions; source geometry, reviewed patches and scale are unchanged. This demonstrates a complete approximate presentation, not survey accuracy or certified architectural recovery. No further Gaussian training/downloads were performed. [Method and limitations](../reconstruction/FLOORPLAN_OPTIMIZATION.md).


### Furnished rough draft and ceiling envelope

A later CPU diagnostic independently estimates an upper point envelope of about 2.53 m, close to the separate user ~2.6 m reference, with sparse high coverage and no certified ceiling plane. Explicit assistant source-image polygons place five approximate furniture footprints; these use partial visible geometry and size priors, not learned automatic detections. Corrected SVG orientation and aligned 3D Top view are presentation changes. Physical scale, poses and reviewed structural evidence remain unchanged. [Technical details](../reconstruction/FLOORPLAN_OPTIMIZATION.md).
