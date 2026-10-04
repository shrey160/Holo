# Opening reference diagnostic

This separate CPU stage uses **RGB corners + source intrinsics + fixed ARKit poses + a user-declared reference size**. It checks a local known-size object without changing the existing sparse/dense/surface baseline. It never consumes captured depth/LiDAR, refines cameras, integrates IMU, or applies scale correction. It does not produce a floorplan. [Staged plan](GROUNDING_PLAN.md), [surface evidence](../reconstruction/SURFACES.md).

**Reviewed diagnostic, 2026-10-04:** `outputs/single-room-grounding-v4` incorporates the user's confirmation of the exact original marks and thickness **below 1 cm** through [the separate source-bound review](../../capture_annotations/single_room_grounding_review.json). Treat thickness as `0 â‰¤ t < 0.010 m`, not exact zero; nominal cover dimensions remain provisional. [Controlled investigation and commands](GROUNDING_DIAGNOSTICS.md). Per-view refinement improves the planar initializer, but cross-view pixel shifts, holdouts and point fitting do not resolve the residual failure. No scale/floor correction. v3 remains an immutable pre-confirmation snapshot. New reviewed report: http://127.0.0.1:8004/.

## Native workflow

From `proto-2`, use the existing uv environment:

```shell
uv sync --locked --extra reconstruct
uv run --locked --extra reconstruct cozmo-grounding outputs/single-room-preprocessing-final outputs/single-room-cli-v2 outputs/my-grounding-editor --source ../test_data/iphn-17/single_room
python -m http.server 8003 --bind 127.0.0.1 --directory outputs/my-grounding-editor
```

Open http://127.0.0.1:8003/. The output initially reports `INSUFFICIENT_OBSERVATIONS` and supplies a local corner editor. The editor copies the selected prepared opening images without rotation, resizing or re-encoding. Images are served locally; the page has no remote scripts or uploads. Initial installation can require internet; subsequent processing is offline.

Select about 5â€“8 clear views with all four cover corners visible and some camera translation. Starting at one physical corner, click a complete perimeter: **0â†’1 is the short width, 1â†’2 the long height**, then the remaining two corners. Use the same physical start corner in every image. Exclude spiral binding and underlying pages; rounded corners need consistent straight-edge intersections. Display clicks map to native image-edge coordinates. Reset/undo, imported corner JSON and an explicit human-review checkbox are available. Views with fewer than four marks are omitted. At most 12 marked frames are admitted.

Enter your annotator identifier, review every exported corner/order and download the JSON. The editor also displays the exact export JSON; if your browser blocks blob downloads, copy it into a separate UTF-8 `.json` file. Put the file in a separate local folder, then calculate a new output:

```shell
uv run --locked --extra reconstruct cozmo-grounding outputs/single-room-preprocessing-final outputs/single-room-cli-v2 outputs/my-grounding-report --source ../test_data/iphn-17/single_room --annotations path/to/grounding-corners.json
```

Use a new output folder; existing results are never overwritten. A downloaded JSON does not alter the currently displayed report. Rerun the command, then serve/open the new result. Human review is a declaration, not independently certified annotator identity. Native picture orientation can appear sideways; this is intentional to preserve K/pose correspondence.

For comparisons against existing accepted stereo pixels and horizontal surface hypotheses, add all upstream paths **when initially preparing the editor and when running the report**:

```shell
uv run --locked --extra reconstruct cozmo-grounding outputs/single-room-preprocessing-final outputs/single-room-cli-v2 outputs/my-grounding-with-surfaces --source ../test_data/iphn-17/single_room --annotations outputs/grounding-evidence/single-room-corner-proposals.json --sparse outputs/single-room-sparse-100-v2 --dense outputs/linux-reconstruction/single-room-dense-100-v1 --surfaces outputs/single-room-surfaces-v2
```

Corner files bind to that exact upstream configuration; a file made without dense/surface bindings cannot silently be reused with different ones. This example uses private trial data present on the development machine; recordings and proposals are excluded from submission packages. Other machines need their own validated captures/derived artifacts and annotations. Source-root rebasing is supported via `--source`.

## Docker workflow

The existing pinned CPU reconstruction environment also supplies grounding; no CUDA or new model is required:

```shell
docker build --target grounding -t holo-grounding:0.2.0 .
docker run --rm --mount "type=bind,source=C:/Shrey_Projs/Recruitements_comp/tkh_cozmo,target=/workspace,readonly" --mount "type=bind,source=C:/Shrey_Projs/Recruitements_comp/tkh_cozmo/proto-2/outputs/linux-reconstruction,target=/results" holo-grounding:0.2.0 /workspace/proto-2/outputs/single-room-preprocessing-final /workspace/proto-2/outputs/single-room-cli-v2 /results/my-grounding-editor --source /workspace/test_data/iphn-17/single_room
```

Replace the host paths with your own. Mount source data read-only and a separate results directory writable. This standalone target does not rebuild/restart Holo or change its captures volume. Holo HTTP reconstruction integration remains subsequent work.

## Geometry and interpretation

- **Planar pose:** general `solvePnPGeneric(..., SOLVEPNP_IPPE)` with the declared rectangle dimensions; retain both alternatives, positive depth, reprojection error, ambiguity and cross-view stationary center/normal spread. A4 is not square; `IPPE_SQUARE` is inappropriate. The dimensions are inputs to PnP, so its fitted size cannot validate them. [Official OpenCV documentation](https://docs.opencv.org/4.13.0/d5/d1f/calib3d_solvePnP.html), [IPPE author](https://github.com/tobycollins/IPPE).
- **Unconstrained size:** closest-ray triangulation of each corresponding corner across the fixed source cameras, with no rectangle/known-size constraint. Check positive depth in every marked view, ray angles, conditioning and reprojection residuals. Measure both width edges, both height edges, diagonals and planarity. Source estimated metres remain unchanged.
- **Sensitivity:** when triangulation passes, repeat with deterministic bounded Â±3 px coordinate perturbations. Report spread and usable trials, not a calibrated confidence interval. Actual corner uncertainty and dimension uncertainty remain unknown unless declared.
- **Stereo:** use only existing accepted depth pixels inside a conservatively eroded object polygon. Do not substitute adjacent floor pixels. Missing support stays missing. Quantitative stereo/plane and floor-candidate comparisons require accepted corner triangulation.
- **Floor candidates:** compare the object plane with horizontal source-world plane hypotheses only after the geometry gate. Semantic identity remains unconfirmed. Unknown notebook thickness prevents identifying its top cover as exact floor height. A supplied thickness yields a user-assumed bottom offset, not independent accuracy.

Defaults require at least 3 views, at least 1.5Â° ray angle for every corner, positive optical depth and no marked residual above 4 px. The local size discrepancy threshold is 5%; stationary PnP center/normal spread limits are 3 cm/15Â°. Thresholds are diagnostic gates, not measurement guarantees. Pixel centers and source distortion remain physically unverified; K is used numerically with native image-edge coordinates, consistent with the existing zero-shift hypothesis. No hidden distortion correction or pose fitting is applied.

Overall status remains `REVIEW_REQUIRED`. `geometry_state` distinguishes `INSUFFICIENT_OBSERVATIONS`, `INSUFFICIENT_PARALLAX`, `DISAGREEMENT_REVIEW_REQUIRED`, `AMBIGUOUS_OBJECT_POSE` and `CONSISTENT_LOCAL_REFERENCE`. Even the last state does not establish room accuracy. Width/height scale suggestions are separate diagnostic ratios; neither is applied.

## Outputs and audits

`manifest.json` binds ingestion/prepared/video and optional sparse/dense/surface manifests, policies, source fingerprint and all artifacts. `views.json` retains exact source K/poses/frame/time/image identities. `reference.json` preserves the declaration. `annotations.json` retains corner/provenance/uncertainty/thickness fields; `annotation_source.json` preserves exact input bytes when supplied. `report.json`, original images, observed/reprojected corner overlays and `index.html` make findings inspectable.

Original ingestion and preprocessing audits are mandatory; optional dense/surface comparisons add their full upstream audits. Independent verification re-reads source associations and recomputes diagnostics, rather than trusting a rehashed report. Publication is atomic; failed staging diagnostics are retained. Ancestor/descendant output overlap with source/upstream/annotation paths is rejected.

```shell
uv run --locked --extra reconstruct cozmo-grounding outputs/single-room-preprocessing-final outputs/single-room-cli-v2 outputs/my-grounding-report --source ../test_data/iphn-17/single_room --verify-only
```

Include the same optional upstream paths if the report binds them. The archived annotation allows verification without the original external corner file; if `--annotations` is supplied, its exact input hash is also checked.

## Historical pre-confirmation single-room trial

User reconfirmed **21 Ã— 29.7 cm as a provisional reference; thickness unknown**. Six assistant visual proposals are explicitly `human_reviewed: false`; marks approximate the rounded colored-cover intersections and still need user correction/review. The opening prepared selection provides 17 candidate images; the diagnostic does not add newly decoded raw frames because usable views already exist.

The exploratory geometry has approximately **0.209 m** baseline and **6.33â€“9.06Â°** maximum corner ray angles. Provisional width edges are **0.2113/0.2136 m** and height edges **0.2936/0.3092 m**. Maximum reprojection error is **10.14 px**, exceeding the 4 px gate; per-view known-size PnP solutions also fail the residual gate. Result: **DISAGREEMENT_REVIEW_REQUIRED**, not validated scale. These exploratory dimensions must not be used to correct the reconstruction.

Accepted object-interior stereo pixels exist in four marked views; two have none. Floor/plane and quantitative object-plane depth comparisons are withheld because the corner triangulation is rejected. Sensitivity is also withheld. Causes remain unresolved: provisional marks, rounded/bent cover/edge selection, actual cover dimensions or calibration/pose assumptions could contribute. No cause or precise floor height is claimed.

Final `outputs/single-room-grounding-v3` publishes 30 hashed artifacts, including archived original proposals, copied native images and six overlays. Earlier v1/v2 previews are superseded by the final provenance/export-fallback view. 86 Windows/Linux tests pass; native and Linux read-only full-chain verification and repeated Windows preservation checks pass. Wheel/source builds and installed native/container/isolated-wheel commands pass. Browser frame selection and undo are inspected; export omits incomplete frames. Actual in-app browser download-path capture timed out; the visible JSON fallback provides the exact export content for a separate file.

The subsequent human confirmation and separate reviewed rerun are now complete; [current diagnostic findings](GROUNDING_DIAGNOSTICS.md). The next architectural milestone is patch-based identity review and supported partial single-room boundaries, retaining unresolved reference calibration. No commit/push was requested for either grounding milestone.
