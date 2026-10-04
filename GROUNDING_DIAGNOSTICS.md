# Reviewed opening-reference investigation

The user confirmed the six original corner marks and reported notebook thickness below 1 cm. The separate reviewed diagnostic incorporates that confirmation without editing the original marks, camera poses, source calibration, scale, dense cloud or surface candidates. [Grounding workflow](GROUNDING.md), [review provenance](capture_annotations/single_room_grounding_review.json).

## Reproduce the reviewed diagnostic

From `proto-2`, use the original source-bound corner file and its separate review record:

```shell
uv run --locked --extra reconstruct cozmo-grounding outputs/single-room-preprocessing-final outputs/single-room-cli-v2 outputs/my-reviewed-grounding --source ../test_data/iphn-17/single_room --annotations outputs/grounding-evidence/single-room-corner-proposals.json --review-confirmation capture_annotations/single_room_grounding_review.json --sparse outputs/single-room-sparse-100-v2 --dense outputs/linux-reconstruction/single-room-dense-100-v1 --surfaces outputs/single-room-surfaces-v2
```

Those development recordings and original corner coordinates are private output files, excluded from the package. On another machine supply that machine's validated captures, derived artifacts and review inputs. A review must bind the exact original corner-file SHA, source-video SHA and every marked rank. Modified/re-exported corner bytes require a new matching review record. Passing this record as ingestion `--annotations` or grounding `--annotations` is invalid; it is only a `--review-confirmation` input.

New reports with a separate review use `holo-grounding-diagnostic-v2`. The exact review bytes are archived as `review_confirmation.json` and bound by the manifest. Existing v1 reports retain their original numerical interpretation and can still be verified; they are not retroactively promoted to reviewed. Original `annotations.json` remains the assistant proposal; the report records the subsequent human confirmation separately. The native CLI and the existing CPU Docker grounding target support the new argument.

Verification without either external input is supported through both archived files:

```shell
uv run --locked --extra reconstruct cozmo-grounding outputs/single-room-preprocessing-final outputs/single-room-cli-v2 outputs/my-reviewed-grounding --source ../test_data/iphn-17/single_room --sparse outputs/single-room-sparse-100-v2 --dense outputs/linux-reconstruction/single-room-dense-100-v1 --surfaces outputs/single-room-surfaces-v2 --verify-only
```

## Controlled checks

These experiments do not replace the accepted triangulation, relax its 4 px limit or alter the baseline:

- Refine both general IPPE object-pose initializations with OpenCV LM, keeping source K and corners fixed. This minimizes per-view rectangle reprojection; declared dimensions remain fitted inputs. Alternatives may converge to the same pose, so convergence is not proof that ambiguity is resolved. [Official OpenCV pose-refinement documentation](https://docs.opencv.org/doc/doxygen/html/d5/d1f/calib3d_solvePnP.html).
- Test symmetric principal-point shifts of −0.5 and +0.5 px as explicit pixel-center hypotheses, rather than silently changing the supplied K.
- Leave out each marked view in turn; triangulate with the remaining views and report both training and held-out residuals. These are diagnostic comparisons, not a rule for cherry-picking accepted views.
- Minimize pixel reprojection error independently for each 3D corner using a deterministic Gauss–Newton point fit with positive-depth backtracking. All camera poses and corner observations remain fixed. This minimizes summed squared errors, not maximum error; its maximum may increase.

## Single-room findings

Published reviewed result: `outputs/single-room-grounding-v4`, available locally at http://127.0.0.1:8004/. The pre-confirmation v3 at port 8003 is preserved.

| Check | Finding |
|---|---|
| Original closest-ray triangulation | Maximum 10.1415 px; rejected |
| Largest residual | Corner 2 at rank 165, approximately 2.751 seconds |
| Per-corner RMS | 2.9058 / 0.5294 / 6.6984 / 2.1628 px |
| −0.5 / +0.5 px principal-point shifts | Maximum 10.1370 / 10.1461 px; both rejected |
| Leave one view out | All six training subsets still rejected; maxima 9.1260–11.3326 px |
| Pixel-objective point fit | RMS 3.7940 px; maximum 10.6775 px; no correction adopted |

Per-view LM refinement reduces the original IPPE RMS considerably:

| Rank | Original best IPPE RMS, px | Refined best RMS, px |
|---|---|---|
| 0 | 18.6430 | 3.5423 |
| 75 | 11.7735 | 1.5124 |
| 120 | 16.7616 | 2.9496 |
| 150 | 19.2000 | 5.9292 |
| 165 | 14.4139 | 5.3610 |
| 180 | 10.9655 | 4.5484 |

The original planar initializer was not a fully minimized per-frame estimate. However, refinement still fails in three views, and the independent cross-view residual persists. Those per-view rectangle residuals do not use ARKit world poses, so ARKit inconsistency alone cannot explain every observed discrepancy under the current rectangle/pinhole assumptions. Half-pixel convention shifts and removal of one view do not resolve the multi-view disagreement. These findings do not uniquely distinguish projection/calibration, object shape, correspondence uncertainty or source-pose errors. The user has confirmed the marks; their numerical uncertainty and physically measured outer-cover dimensions remain unspecified.

## Thickness and floor interpretation

Preserve `0 ≤ t < 0.010 m`, exact thickness unknown. Do not substitute zero or use this bound to modify image residuals. A cover lying flat and stationary on a floor would provide a conditional top-to-bottom offset along world +Y. For plane `(n,d)` and cover-center signed distance `s`, propagate `s − n_y t`, reversing interval endpoints and their inclusive/exclusive flags when required. This still assumes gravity alignment, flat placement and the correct architectural floor identity.

The reviewed result retains the bound but **withholds floor comparison** because the geometry gate fails. No exact floor height, scale correction or accepted local reference is produced. Object-interior stereo support remains available as support counts; no quantitative comparison is promoted from rejected corner geometry.

## Follow-up

Continue image-linked floor/wall identity review and conservative partial boundaries using the unchanged baseline, while keeping reference calibration unresolved. P01 is bed evidence; P02 is a local floor hypothesis. Do not close missing spans or report verified room dimensions. Resolving physical calibration requires additional evidence, such as a physically measured rigid rectangle/calibration capture and its uncertainty; repeatedly optimizing the same four corners cannot supply independent accuracy.

The implementation has no added dependency. Five new analytic tests cover review identity, invalid/contradictory intervals, strict endpoint reversal, fixed-camera point fitting, disagreement retention, portable archived-review verification and rehashed false-bound rejection. The full 91-test suite passes Windows and Linux.
