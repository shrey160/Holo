# Grounding diagnostic and partial-floorplan plan

Prepared 2026-10-04 after the verified [surface evidence stage](../reconstruction/SURFACES.md). **Implementation, corner confirmation and the reviewed mismatch investigation are delivered**; [workflow](GROUNDING.md), [current findings](GROUNDING_DIAGNOSTICS.md). The reviewed trial retains the sub-centimetre thickness bound but still fails the 4 px gate; no scale/floor correction is justified. Next perform image-linked architectural identity review and supported partial single-room boundaries while retaining unresolved reference calibration. Later architectural milestones remain pending. The following design preserves the original stage boundaries.

## Inputs and boundary

Use the existing video-bound `opening-a4-reference` declaration: user-reported 0.210 Ã— 0.297 m, candidate interval 0â€“5 seconds. That interval does not establish visibility in every frame. The photograph can help identify the same object but supplies no in-video position, calibration or measured dimensions by itself. A book's actual outer cover may differ from nominal A4: keep `USER_REPORTED` dimension provenance and unknown uncertainty until measured. Unknown cover thickness prevents equating its top plane with exact floor height.

Use original/native-grid RGB, exact per-frame K and optical camera-to-world poses from the verified ingestion/preprocessing chain. Additional reference frames may come from the opening raw video if the prepared selection does not contain enough useful views; preserve exact frame/time associations and audit derived images. For stereo comparison, only existing selected dense frames and accepted depth observations are admitted. No LiDAR/captured depth, IMU integration, pose refinement, raw modification or automatic rescaling. Record this as **RGB + poses + known-size human reference**, separately from the existing no-grounding baseline.

## Milestone 1: source-bound corner annotation

- Inspect the first five seconds; propose approximately 5â€“8 sharp frames with all four outer corners visible, including usable camera translation where available. Reject blur, occlusion and uncertain cover boundaries. Do not select near-identical views merely to meet a count.
- Provide a small local annotation view for four consistently ordered corners. Store actual rectangle width/height edge identity, frame ID, image/video hashes, native dimensions, source time, pixel convention, annotator and optional corner uncertainty. Display resizing must map clicks back to native coordinates; no hidden orientation change.
- Keep human-reviewed annotations in a separate file bound to the source, rather than editing ingestion or reconstruction artifacts. An automatic detector/tracker is optional later, after the manual geometry path is validated.

Deliverable: auditable corner JSON and overlays. If useful corners/baseline are absent, report insufficient observations and continue surface review without inventing a grounding result.

## Milestone 2: diagnostic geometry, with two distinct checks

**Object-pose check.** Use four known planar corners and each frame's exact K with OpenCV `solvePnPGeneric(..., SOLVEPNP_IPPE)`. A4 is rectangular, so use general IPPE rather than its square-only variant. Retain alternative solutions, positive-depth/reprojection checks and explicit ambiguity. Transform object poses through the fixed source camera poses and evaluate whether the stationary object's position/normal agrees across frames. A small reprojection residual alone is insufficient when multiple planar poses remain plausible. [OpenCV PnP methods and multiple solutions](https://docs.opencv.org/4.12.0/d5/d1f/calib3d_solvePnP.html), [IPPE author's ambiguity discussion](https://github.com/tobycollins/IPPE/blob/master/README.md).

**Unconstrained size check.** Triangulate the marked corners across fixed source cameras without enforcing the known rectangle dimensions. Require positive optical depth, sufficient ray angle, consistent corner identity and bounded reprojection residual. Measure both opposite width edges, both height edges and diagonals; compare with the declared dimensions. Known-dimension PnP cannot independently validate size, because its input already fixes that size. PnP/stereo agreement is also a shared-calibration diagnostic, not independent room-accuracy proof.

Compare accepted stereo depths with the estimated object surface only where supported pixels actually lie on the object; keep floor pixels and object pixels distinct. Missing stereo support remains missing. Resolve pixel-coordinate conversion explicitly so annotations, K and projection use the same rays; preserve the existing physically unverified calibration/distortion assumption and report it.

Report width/height discrepancies, per-view object pose spread, reprojection/parallax evidence, stereo disagreement and sensitivity to corner perturbations. Unknown size/corner uncertainty stays unknown. Perturbation spread is a sensitivity diagnostic, not a calibrated confidence interval. Suggested states: `CONSISTENT_LOCAL_REFERENCE`, `DISAGREEMENT_REVIEW_REQUIRED`, `AMBIGUOUS_OBJECT_POSE`, `INSUFFICIENT_PARALLAX`, `INSUFFICIENT_OBSERVATIONS`.

Deliverable: separate grounding report with visual residuals, manifest bindings, assumptions and `scale_applied: false`. Compare local plane orientation/offset with P02, retaining book thickness as unresolved if unknown. A possible uniform-scale ratio is diagnostic only; inconsistent width/height ratios indicate that a single global scaling factor is not justified. No existing geometry is overwritten.

## Proposed module and verification design

Keep `cozmo_reconstruction/grounding/` separate from source parsing and future floorplan inference. Frozen request/policy and annotation records belong in `models.py`; source/hash/native-coordinate validation in `annotations.py`; PnP, triangulation and plane transforms in `geometry.py`; comparisons/sensitivity/status in `analysis.py`; full source audit and atomic publication in `pipeline.py`; recomputation in `verification.py`; bounded native/container CLI in `cli.py`. Existing NumPy/OpenCV/PyCOLMAP CPU runtime is sufficient; no new model download is planned.

Behavioral checks should cover a known rectangle with translated cameras, intentional scale disagreement, width/height ordering, resized-click conversion, pure rotation/weak baseline, planar ambiguity, behind-camera corners, invalid/self-intersecting annotations, unknown thickness, missing dense support, source/hash tampering and no input mutation. Run the real single-room trial separately. Preserve source and baseline hashes before/after and keep failed stages diagnostic-only. Grounding remains useful even when it concludes insufficient evidence.

## Milestone 3: reviewed surface identities

Bind review decisions to `single-room-surfaces-v2` and exact source overlays. Record floor, wall, furniture, mixed or unknown evidence with reviewed image regions/patches; do not promote an entire geometrical plane merely because one region is architectural. P01's bed evidence rejects that region as floor. P02 is a local opening-floor hypothesis; the ground object's support plane may strengthen or contradict it. Review vertical candidates against RGB, retaining curtains/furniture and unsupported spans as unresolved or rejected evidence.

Deliverable: a separate provenance-bound review artifact, supporting images and explicit rejected/unknown regions. If the geometry does not contain enough wall evidence, identify the missing coverage before topology inference.

## Milestone 4: partial single-room floorplan

Project reviewed wall patches into a supported floor coordinate system while keeping their source-world transform. Extract only observed wall spans. Label any extrapolated intersections separately; do not close a polygon or assume rectangular/orthogonal rooms when evidence is missing. Export an inspectable partial plan, source-image links and measurement status. Claim measured area/dimensions only when independently checked with physical measurements; the grounding object used as an input is not held-out evaluation truth.

Then address the double-room pose-transition event before reconstructing/stitching its doorway. Integrate validated CLI stages into Holo after their contracts stabilize. A closed property floorplan, local-drift repair and dimensional-accuracy claims remain subsequent work.
