# Reference-object declarations

`single_room.json` and `double_room.json` declare the user-provided 21 Ã— 29.7 cm A4-size book/paper in the opening of those exact recordings. Each file names its own `wide.mp4` SHA-256. These are optional ingestion inputs, not detected-object output or independent evaluation ground truth.

[single_room_grounding_review.json](single_room_grounding_review.json) is a separate chat-confirmation record, **not an ingestion declaration or CLI corner file**. It binds the original proposed-corner hash/video and records the user's confirmation of corner accuracy and thickness `0 â‰¤ t < 0.010 m`. It does not specify exact zero thickness or measured cover dimensions. Pass it through grounding `--review-confirmation` alongside the exact original corner file. The new v4 report incorporates this record and retains the unresolved residual failure; source/baseline and historical reports remain preserved. [Reviewed diagnostic workflow and findings](../docs/grounding/GROUNDING_DIAGNOSTICS.md).

## Declaring a new reference

Create a new JSON file using either existing file as a template, then set:

| Field | Meaning |
|---|---|
| `schema_version` | Current declaration schema: `1` |
| `source_video_sha256` | SHA-256 of the complete original video |
| `reference_objects[].id` | Unique nonempty reference ID within the declaration |
| `width_m`, `height_m` | Positive actual dimensions in metres |
| `dimensions_source` | `USER_REPORTED` for the current supported schema |
| `visibility_verified` | `false`; ingestion does not detect visibility/corners |
| `candidate_window_seconds` | Ordered nonnegative start/end relative to capture origin; must intersect camera records |
| `label`, `placement`, `usage` | Describe the object, placement and intended assistance |
| `dimension_uncertainty_m` | Optional recorded measurement uncertainty; existing user declarations use `null` |

The opening window `[0, 5]` only selects candidate frames. It does not assert that the object is visible throughout. The capture guide uses one object at the video opening only; later rooms do not require another placement. An optional separate object photo is stored by the web layer in `reference/` and bound to the same video. It remains supplementary evidence, without detected corners or applied scale.

PowerShell example for the video hash:

```powershell
(Get-FileHash -LiteralPath "C:/captures/session/wide.mp4" -Algorithm SHA256).Hash.ToLowerInvariant()
```

From `proto-2`, pass the new declaration with `cozmo-ingest --annotations capture_annotations/my-session.json` alongside source/output arguments. Existing examples only work for their matching videos. Omit `--annotations` to ingest without a prior. The web form creates an equivalent hash-bound declaration automatically for its uploaded video.

Ingestion records candidate source-frame indices and leaves corner localization/scale estimation `NOT_RUN`, with `scale_applied: false`. Do not edit a published bundle annotation to add a measurement; create a new run or a separate future-stage artifact. [Capture/grounding guide](../capture.md) Â· [Main commands](../README.md).


`single_room_objects_v1.json` is a separate assistant visual review for approximate furniture footprints. Native RGB polygons, camera ranks/image hashes, height bands and explicit minimum extents are used by the opt-in viewer publisher. It does not change structural acceptance or constitute user-confirmed object measurements. [Method](../docs/reconstruction/FLOORPLAN_OPTIMIZATION.md).
