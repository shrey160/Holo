# CPU floorplan refinement

Gaussian-splatting refinement is deferred by the user. This stage works from the existing accepted RGB stereo cloud, fixed source poses and region-reviewed structural evidence. It requires no model weights, new numerical dependencies or GPU inference. [Report notes](FINAL_REPORT_NOTES.md), [original plan viewer](RECONSTRUCTION_VIEWER.md).

## What changes

The previous occupancy plan mixed the bed, desk, curtains, walls and isolated reconstruction noise. A new **Structure-focused** layer emphasizes occupied columns assigned to existing vertical multiview plane candidates with support at multiple heights. The original **All observations** layer remains available for comparison; filtered points are still retained in the underlying cloud and original result.

The CPU derivative uses 10 cm floor-coordinate cells and fixed engineering thresholds: heights 0.6–2.4 source-estimated metres, 40 cm height bands, at least four voxels per qualifying band, at least two bands and 80 cm of supported vertical extent. Sparse singleton height outliers cannot supply extent. A cell also needs at least two neighboring qualifying cells, a connected component of at least six cells and at least 50 cm component extent. These filters reduce low furniture and isolated noise; tall furniture and curtains can survive. Height persistence is a geometric heuristic, not a semantic wall label or independently calibrated confidence.

Existing vertical multiview plane candidates provide provenance for robust top-down line suggestions. [OpenCV Huber line fitting](https://docs.opencv.org/3.4.15/d3/dc0/group__imgproc__shape.html) refits retained samples without a right-angle prior. Refits differing by more than 15 degrees from the source plane are withheld. Samples beyond 8 cm perpendicular residual are excluded from suggested extents; 15 cm along-line bins need at least 20 retained samples and 80 cm vertical extent. Only adjacent supported bins join; spans below 45 cm are withheld. Empty bins, endpoints, source geometry, camera poses and scale remain unchanged. Suggestions do not enter reviewed wall geometry or infer a closed polygon.

The browser defaults to the structure-focused layer for new bundles, offers fitting to its evidence extent, and keeps camera path, reviewed floor/wall overlays, optional unreviewed line suggestions and the original occupancy comparison. It also downloads the plan JSON with thresholds, retained cells, per-plane decisions and line suggestions. Older published bundles remain compatible.

## Image review

The separate `capture_annotations/single_room_regions_floorplan_v2.json` retains the earlier floor/P07 decisions and replaces three broad P12 mixed regions with conservative polygons over the visible poster-covered wall in source ranks 690, 750 and 1065. Window/curtain, bed/pillow and desk areas are outside those polygons; unmarked pixels remain unreviewed. The original review/result are preserved. New marks are **assistant visual decisions**, not user-confirmed architecture. Multiple plane estimates may represent different patches of the same physical wall; they are not automatically merged or counted as separate room walls.

The existing boundary command enforces exact image/observation hashes, accepted stereo samples, qualifying source views and camera baselines before any new projected patch is admitted. Missing floor–wall junctions and corners remain unverified.

## Reproduce

Use the existing main environment:

```shell
uv sync --locked --extra web --extra reconstruct
cozmo-boundaries outputs/single-room-surfaces-v2 outputs/single-room-boundaries-v2 --sparse outputs/single-room-sparse-100-v2 --prepared outputs/single-room-preprocessing-final --bundle outputs/single-room-cli-v2 --dense outputs/linux-reconstruction/single-room-dense-100-v1 --source ../test_data/iphn-17/single_room --grounding outputs/single-room-grounding-v4 --review capture_annotations/single_room_regions_floorplan_v2.json
cozmo-publish-reconstruction outputs/single-room-boundaries-v2 outputs/holo-reconstruction/single-room-floorplan-v3 --surfaces outputs/single-room-surfaces-v2 --sparse outputs/single-room-sparse-100-v2 --prepared outputs/single-room-preprocessing-final --bundle outputs/single-room-cli-v2 --dense outputs/linux-reconstruction/single-room-dense-100-v1 --source ../test_data/iphn-17/single_room --grounding outputs/single-room-grounding-v4 --label "Single room - refined plan v3"
```

Published output folders must be new. The ordinary native Holo server and Docker reconstruction override display the new bundle without GPU Python libraries. [Setup](WEB_SETUP.md).

## Measurement boundary

The user-reported ceiling height is **about 2.6 m**, stored independently in [the evaluation reference](evaluation_annotations/ceiling_reference.json). This stage does not read that file, detect a ceiling or normalize scene scale against it. Measurement method, uncertainty and capture binding remain unspecified. A later ceiling comparison should distinguish recovered height from user-provided reference assistance.

Physical accuracy, unresolved opening-reference calibration, unidentified P05 geometry, room closure, room area, doors and double-room stitching remain separate issues. Cleaner graphics and increased patch coverage do not establish a completed dimensioned floorplan.

## Recorded result (2026-10-04)

The revised source-bound boundary result has 81 verified artifacts, the unchanged 11 local floor cells, the original P07 0.599 m projected patch and a P12 0.898 m projected patch supported by three source views. Both patches concern the poster-covered wall; they are not two room walls and neither has near-floor observations certifying a junction.

The final presentation is `outputs/holo-reconstruction/single-room-floorplan-v3` (**Single room - refined plan v3** in Holo). Structure focus retains 50 supported cells and 76,349 source voxels, with three optional unreviewed line suggestions. The original 878,459-voxel source and 120,000-point display are retained. Position/color/PLY bytes are identical to the original viewer bundle. The earlier broad-filter preview is archived privately under `outputs/floorplan-evidence/preview-v2`; it is not the final result.

All 115 tests pass on Windows and Linux. The source-chain audit, no-overwrite publication, native/Docker HTTP hashes and preservation checks pass: 1,512 protected files and all 10 capture jobs are unchanged. Browser checks cover layer comparison, suggestions and fitted extents. Private evidence is under `outputs/floorplan-evidence`. No commit/push or additional Gaussian download/training was performed.

Next work is source-image coverage/identity review, testing whether differently oriented poster-wall plane patches can be reconciled without hiding source inconsistency, recovering missing architectural boundaries, and a ceiling-height diagnostic against the approximate external 2.6 m reference once floor/ceiling correspondence is supported. Room closure and physical dimensions remain unresolved.


## Complete rough plan (user-requested approximation)

The user explicitly requested a complete room plan even with errors. The new opt-in `--rough-room` publisher completes a **rectangular hypothesis** instead of limiting the drawing to observed patches. `viewer/rough_room.py` owns a deterministic CPU fit: one longest interval per candidate plane, circular orientation consensus modulo 90 degrees, 5–95% projected endpoint bounds extended to retain reviewed patches, and four inferred corners/walls. Three candidate planes and two orientation families are required. Candidate identities can remain ambiguous; no plane is promoted to reviewed evidence.

The entrance is estimated at the first outside-to-inside capture-path crossing (nearest-start-edge fallback when no crossing exists). Its 0.8 m width and swing symbol are assumptions. The closed footprint, estimated dimensions/area and external ceiling reference live only under `rough_room` / `inferred_room_completion`; certified scene closure, source poses, source scale and boundary evidence stay unchanged. The measured ceiling is displayed separately and does not calibrate the plan.

For this room, `single-room-complete-v1` (**Single room - complete rough plan**) gives approximately **3.2 × 4.1 source-estimated m**, approximately **13 m²**, with the user-reported **about 2.6 m ceiling**. All four full walls are inferred; blue patches retain the actual reviewed positions without snapping. Furniture/windows are not localized. This is a complete rough draft, not a surveyed floorplan.

Append these options to the preceding publisher command, use a new output directory, and choose the new label:

```shell
cozmo-publish-reconstruction outputs/single-room-boundaries-v2 outputs/holo-reconstruction/single-room-complete-v1 --surfaces outputs/single-room-surfaces-v2 --sparse outputs/single-room-sparse-100-v2 --prepared outputs/single-room-preprocessing-final --bundle outputs/single-room-cli-v2 --dense outputs/linux-reconstruction/single-room-dense-100-v1 --source ../test_data/iphn-17/single_room --grounding outputs/single-room-grounding-v4 --label "Single room - complete rough plan" --rough-room --ceiling-reference evaluation_annotations/ceiling_reference.json
```

Holo defaults to **Complete rough plan** for this result. **Structure-focused evidence** and **All observations** remain selectable. Download the complete SVG or its JSON assumptions/evidence. Optional `rough-room.svg` is hash-bound; the read-only API continues to accept original eight-asset bundles and denies unsigned/unknown assets. No extra dependencies, LiDAR or Gaussian training are used. The existing RGB 3D display remains available below the plan.

120 behavioral tests pass on Windows and Linux, including rotated rectangles, inferred closure, source immutability, entry placement, degenerate candidates, ceiling/scale separation, valid SVG and optional-asset tamper protection. Tests check software behavior, not physical accuracy. Private publication/validation/browser evidence is under `outputs/rough-room-evidence`.


## Ceiling estimate, orientation and approximate furniture

The furnished result is `single-room-complete-v2` (**Single room - furnished rough plan**). The source room polygon and estimate of 3.2 × 4.1 m are unchanged. SVG now maps floor v upward, correcting its earlier vertical inversion; the entrance is at the bottom left on the long wall. Evidence/occupancy overlays use the same upward convention, and the 3D Top camera aligns with the room axes. These are display transforms, not source camera corrections. The catalog lists the most recently published manifest first.

`viewer/ceiling.py` computes a provisional upper-envelope estimate without reading or using the external ceiling reference: inside the rough rectangle, select heights 1.8–4 m, group into 25 cm cells, require at least 20 upper voxels per cell, take each cell's 98th height percentile and then the 90th percentile of supported cell tops. At least 12 cells are needed. This suppresses singleton outliers and balances spatial density. The recorded estimate is **2.532 m**, supported by 106 upper cells and 61,013 upper voxels. The 85–95th tile-top spread is about **2.47–2.57 m**; this is a descriptive support band, not a calibrated confidence interval. Only 16 cells (about 7.6% of inferred room area) are within 8 cm of the estimate. A ceiling plane is **not verified**: coverage termination, wall tops and tall objects can imitate a ceiling. Floor gauge and physical scale remain provisional. User height ~2.6 m stays separate; it did not generate or tune the estimate.

The height slider clips points above its chosen height. Point disappearance near 2.5–2.6 m is consistent with the cloud envelope but is not independently sufficient ceiling evidence. Holo displays the estimate separately and provides an **Estimated ceiling slice** button.

`viewer/objects.py` projects accepted source cloud points into calibrated source RGB, uses a 3-pixel nearest-depth buffer with 12 cm tolerance to reduce background leakage, intersects explicit object polygons and height bands, and derives 5–95% floor extents. Source image SHA-256, camera ranks, dimensions and polygon validity are checked. Minimum footprint priors are explicit and only used where a partial view is too narrow; footprints are bounded by the inferred room. No ML model downloads or automatic semantic-detection claim are involved.

The separate [object region review](capture_annotations/single_room_objects_v1.json) contains **assistant visual annotations** for the bed, desk, office chair, wardrobe and folding chair. Clockwise-rotated previews were used for inspection, then their coordinates were converted back to the native 960×540 RGB grid. Wardrobe uses two views; other objects currently use one. Footprints may be truncated, enlarged by priors, affected by occlusion or slightly overlap. Object positions are rough hypotheses, not independent measurements. JSON archives the annotations, hashes, admitted sample counts, bounds, priors and source views; the SVG draws the footprints. A separate **Approximate object footprints** checkbox shows their outlines in 3D without filling or modifying the cloud.

For a new result, append `--object-review capture_annotations/single_room_objects_v1.json` to the opt-in rough-room command and use a new output path/label. The publisher computes the ceiling envelope automatically in rough-room mode. Old results remain immutable. No LiDAR, new reconstruction, grounding correction or Gaussian training is performed. All 125 behavioral tests pass; new cases cover ceiling/reference independence, sparse coverage, vertical orientation, occlusion and source-bound object priors.
