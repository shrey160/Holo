# Native two-room video test — 5 October 2026

Tested the other Sensor Recorder export: workspace `test_data/iphn-17/zips/double_room.zip` (74,348,548 bytes). SHA-256 `7034c5e8af4d05e22e9a20498b57898ef5936ccc391fd4982fda7a125bda4fc0`. Original ZIP unchanged after the run. No source poses, scale, known-object dimensions or measured ceiling values were modified/applied.

**Outcome: dense reconstruction succeeded; automatic floor-plan completion failed.** This is not a passing two-room reconstruction or stitched-plan result.

| Stage | Observed result |
|---|---|
| Original input verification | PASS: 3,949 frames; 16 canonical artifacts; raw sensor values preserved |
| Preprocessing | 240 selected views; 515 artifacts verified; review findings retained |
| Fixed-pose sparse | 100 views, 2,797 accepted points; largest track component 58 views; weak geometry signal |
| Dense support admission | 82 views; 18 excluded for insufficient accepted-track connections |
| Native CUDA RGB stereo | Completed; 468,728 dense voxels; 4,027,499 accepted depth pixels |
| Surface extraction | Completed; architectural identities/physical accuracy unverified |
| Automatic room completion | FAIL: `DENSE_ROOM_SUPPORT_INSUFFICIENT`, “Candidate coverage is too narrow for a rough room” |
| Closed plan, room dimensions, ceiling | Not generated |
| Multi-room segmentation/stitching | Not implemented |
| Original full job time | 675.381567 s (about 11.3 minutes), ending at the failed plan stage |

Original Holo job: `6927cd39123049a492ae9e3c2165be63`. It remains `FAILED` at `ESTIMATING_ROOM`; verified raw/canonical/preprocessed/sparse/dense/surface artifacts are retained under `outputs/web-data-native/jobs/`. The failure gate was not relaxed, and the single-room estimator was not changed for this test.

To let the user inspect the completed geometry, a **separate partial-evidence viewer** was published after independently verifying the upstream surface/dense chain (206 surface artifacts verified). It uses the same unconfirmed floor candidate P06 for a rigid display transform, all source cloud points, a deterministic 120,000-point display subset, capture path and observed occupancy. Four supported span suggestions from fourteen raw candidate spans are diagnostic only. There is no rectangle, doorway placement, closed polygon, area or ceiling estimate.

Open [the partial result in Holo](http://localhost:8000/?reconstruction=two-room-dense-partial-20261005#reconstruction). Use **All observations** for the broader top-down coverage; structure-focused evidence has only 58 persistent cells. The 3D controls support orbit, top view, pan and zoom. Isolated stereo points influence the initial cloud framing; this view is not a calibrated mesh.

All eight viewer assets returned HTTP 200 and matched their manifest hashes. [Machine-readable test evidence](test-summary.json), [observed occupancy](observations.png), [partial span/capture-path SVG](partial-spans.svg). The native app stays on port 8000 with its existing capture history. Local test helpers/logs are in `outputs/double-room-test-20261005/`; no fresh model download or Docker run was needed.

Reproduce the automatic test by uploading the same ZIP in Holo with **Dense room reconstruction + ceiling estimate** selected. Use a fresh job; the original failure and partial viewer remain preserved. Reproduction of a two-room *closed plan* requires further implementation: room segmentation, connector coverage and per-room supported wall fitting. This test does not establish that simply relaxing support thresholds would recover accurate geometry.
