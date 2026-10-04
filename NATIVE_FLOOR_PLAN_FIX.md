# Native dense floor-plan correction

The floor-plan regression recorded in error baseline `d9723e2` is corrected in the automatic dense room estimator. The original failing result and its [frozen evidence](NATIVE_DENSE_REGRESSION.md) remain unchanged.

## Cause and change

`dense_automatic.dense_room` passed raw `candidate_spans` directly into rectangular completion. These spans project every occupied part of a vertical candidate plane onto its floor intersection. They do not require vertical coverage at each endpoint. Extra low-height or poorly supported plane extensions could therefore determine the outer rectangle. Native plane fitting produced a different set of candidates from the earlier Docker run, exposing this sensitivity. The native CUDA backend itself was not shown to corrupt geometry.

The estimator now computes the existing `structure_plan` first and fits its `suggested_spans`. That pipeline retains neighboring occupied columns with at least two supported height bands and 0.8 m of vertical extent, refits each line against the source plane, and retains only contiguous supported intervals. Raw projections stay in `plan.json` for diagnosis. The room records the fitting method, support counts, thresholds and limitations in `boundary_support`.

Insufficient persistent support stops with `DENSE_ROOM_SUPPORT_INSUFFICIENT`; there is no fallback to the oversized raw envelope. This applies to future automatic dense jobs on both native and Docker backends. CPU sparse previews and the separate manually reviewed completion workflow retain their existing behavior.

## Same-cloud comparison

| Quantity | Error baseline | Corrected plan |
|---|---:|---:|
| Approximate dimensions | 4.539 × 4.055 m | **3.147 × 3.706 m** |
| Approximate area | 18.405 m² | **11.662 m²** |
| Provisional ceiling | 2.551 m | **2.573 m** |
| Dense source points | 848,220 | 848,220 |
| Display points / stereo views | 120,000 / 99 | 120,000 / 99 |
| Entrance method | Nearest edge to capture start | First outside-to-inside path crossing |

The revised footprint changes which upper-height tiles enter the ceiling envelope, explaining the small ceiling change. The ceiling algorithm and floor frame are unchanged. No expected 3 × 4 m dimensions, user-reported ceiling height, grounding measurement, source rescaling or furniture labels were used. These remain approximate source-scale estimates: occlusion may shorten supported wall ends, while tall furniture and curtains may still qualify.

The corrected result is [available in Holo](http://localhost:8000/?reconstruction=native-dense-floor-plan-fixed-v1#reconstruction). It was published to a new catalog directory from native job `ae77c443f85f449abad2c0598d4c7648` using `publish_dense`, the same audited publisher called by automatic reconstruction. This took 88.2 seconds of CPU audit/publication. Stereo inference and surface extraction were not rerun; the retained surfaces were independently recomputed for verification. The original job history and download still describe its original error result; select the separately named corrected result in Reconstruction.

## Verification and reproduction

187 native Windows tests pass, including a full synthetic floor/four-wall test where a two-metre low-height extension enlarges raw completion by over 30% but does not change the filtered room. Another test checks that missing persistent support fails visibly. Ruff checks and formatting pass. No frontend source changed.

The retained publication passes the full upstream dense/surface audit and viewer asset integrity checks. SHA-256 checks preserve 80 historical/source files, including the original job, failing viewer and manifests. Corrected `positions.bin` and `colors.bin` exactly match the failing viewer; the floor display transform is identical. [Committed comparison and corrected SVG](docs/regressions/native-dense-2026-10-04/fix/README.md).

For a fresh native run, follow [native dense setup](NATIVE_DENSE.md), start the updated server, and upload the same complete `single_room.zip` with Dense selected. For an existing retained job, CPU-only republication can use the same domain API:

```python
import json
from pathlib import Path
from cozmo_reconstruction.dense.models import DenseRequest
from cozmo_reconstruction.surfaces.models import SurfaceRequest
from cozmo_reconstruction.viewer.dense_automatic import publish_dense

job = Path("outputs/web-data-native/jobs/ae77c443f85f449abad2c0598d4c7648").resolve()
ranks = tuple(json.loads((job / "dense-selection.json").read_text())["selected_ranks"])
dense = DenseRequest(job / "reconstruction", job / "preprocessing", job / "bundle",
                     job / "dense", job / "raw", ranks)
publish_dense(SurfaceRequest(dense, job / "surfaces"),
              Path("outputs/web-data-native/reconstructions/my-corrected-room").resolve(),
              "Corrected room")
```

Use a new output directory. Original raw/prepared/sparse/dense/surface inputs must remain available for audits. Holo reads the newly published catalog result; existing captures are never silently rewritten. A new full upload or GPU inference was not repeated during this correction, and Docker execution was not rerun. Architectural accuracy, object localization and multi-room segmentation remain separate work.
