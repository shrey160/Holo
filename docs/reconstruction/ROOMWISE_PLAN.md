# Room-wise capture-route analysis

6 October 2026. **Implemented: provisional room scanning stays, local wall evidence and an automatic partial-result viewer. Not completed: confirmed doorway crossings, closed two-room floor plans or stitched adjacency.**

The capture protocol allows either Room A â†’ doorway â†’ Room B, or Room A â†’ passage â†’ doorway â†’ Room B. An exit to a corridor is not required. Recording a door's wall/corners without crossing it must not alone create another room. The grounding object appears only at the start; this stage neither detects it nor applies its dimensions.

## Modules and data flow

`viewer/route.py` uses timestamped optical camera-to-world poses from the audited sparse input mapping. It finds scanning stays using horizontal position and viewing direction: an 8-second window, 90th-percentile radius â‰¤0.85 m, â‰¥70Â° horizontal turning, and sustained qualifying window centers for â‰¥4 seconds. Gaps >2 seconds invalidate windows. The first 3 seconds are excluded by protocol, not object detection. Nearby stays reuse a provisional room identity within 1.2 m. A short doorway scan does not necessarily qualify. These thresholds are heuristics, not trained or calibrated room classifiers.

The output includes room anchors, scanning intervals/ranks, diagnostic windows and unresolved transition intervals. It never assigns a measured crossing timestamp or doorway width. A long scan inside one large room can still produce a false split; a long corridor scan can resemble a room; close rooms can merge. Revisit identity needs image/geometry confirmation.

`viewer/local_rooms.py` associates unchanged source-cloud voxels with accepted stereo pixels contributed by each scanning stay. Earlier approach frames looking within 60Â° of the stay anchor can add geometry, and are recorded separately. Membership uses the original voxel cells, masks and sampling grid, rather than nearest-camera distance. A cell visible through a doorway can support both rooms. Source index selections have deterministic SHA-256 digests.

Each region gets a separate seeded 12-plane extraction budget, including previously unassigned source voxels. Plane admission still requires multiple views, baseline and connected patch support. View-sample requirements increase proportionally for the finer upstream pixel grid (600 samples at stride 2 versus the original 150 at stride 4), so finer sampling cannot weaken admission. Height-persistent spans supply the existing rectangle fitter; raw intervals cannot rescue a failed fit. At least 80% of scanning camera positions must lie within the proposed footprint with 0.2 m tolerance. Approach cameras are excluded from that occupancy test.

The same unconfirmed floor frame is shared across rooms. This preserves relative coordinates but does not resolve floor identity, pose drift or scale. Ceiling estimation runs independently for a region only after its footprint passes. Wall tops and furniture can still mimic a ceiling.

`viewer/dense_automatic.py` keeps the existing single-room path when fewer than two distinct stays qualify. With multiple stays, it publishes local evidence even when one or all footprints fail. The result explicitly returns `PARTIAL_ROOMWISE_EVIDENCE` and the completed/total room counts; missing room dimensions and ceilings remain absent. This is a publication success, not a successful closed-plan measurement. Required dense processing never becomes a sparse fallback.

`viewer/roomwise_svg.py` and frontend `RoomwisePlan.tsx` display the regions in common coordinates, scanning paths, unresolved connectors and local supported spans. Each region can be inspected separately. Failure explanations stay visible; the original observed cloud remains available in interactive 3D.

## Actual two-room outcome

Cached native job `6927cd39123049a492ae9e3c2165be63` was replayed through the audited dense/surface chain, without repeating stereo or changing its original failed state.

| Region | Provisional scanning interval | Source voxels associated | Supported spans / distinct surfaces | Closed outline |
|---|---|---:|---:|---|
| R01 | 10.505â€“35.511 s | 257,119 | 2 / 2 | Unavailable |
| R02 | 44.501â€“65.824 s | 210,850 | 4 / 2 | Unavailable |

The passage is retained between those scanning intervals. Source frame inspection supports the two-room interpretation, but no manually selected timestamps or measurements were used by the algorithm. The two regions still lack at least three independently supported surface candidates for completion. Counts are per-region associations and can overlap; they are not a partition of the cloud.

New viewer: [two-room route review](http://localhost:8000/?reconstruction=two-room-route-review-20261006-v2#reconstruction), 468,728 source voxels, 82 stereo views and 120,000 display points. Nine signed assets passed integrity checks. Independent local derivation reproduced the published room-wise report numerically (1.261 s for that local computation on this machine; upstream audits and original stereo excluded). The source ZIP SHA remains unchanged. [Frozen review evidence](../regressions/roomwise-2026-10-06/README.md).

Dense display paths are sorted by source frame rank, because backend image IDs need not be chronological. A separate regression test checks that order. The original single-room recording produces one route identity and its existing 3.146702 × 3.706239 m / 2.572861 m ceiling estimates recompute unchanged. Synthetic geometry tests produce two separate approximately 3 Ã— 4 m rooms, retain shared coordinates, and verify that a wall-top envelope is labelled provisional. **198 Windows tests passed** with native process permissions; Ruff, TypeScript and the frontend build passed. Docker and fresh GPU inference were not rerun for this change.

## Reproduce from retained dense intermediates

From the prototype root, with the matching original job and source inputs retained:

```shell
uv run --locked --extra reconstruct python scripts/replay-roomwise-plan.py --job outputs/web-data-native/jobs/6927cd39123049a492ae9e3c2165be63 --output outputs/roomwise-new-review --label "Two-room review"
```

Use a new output folder. To make it appear in Holo, choose a new directory under the configured data root's `reconstructions/`. The command audits both parent chains and refuses to replace existing outputs. New automatic dense uploads/retries use the same room-wise branch when their trajectory qualifies.

## Next engineering step

The route split is useful but has not solved the wall evidence problem. Validate the common floor datum and local source overlays; add doorway/image confirmation to transition candidates; then improve room-local wall evidence and view selection without accepting furniture spans or fitting an envelope across both rooms. Only supported region outlines should be joined, with shared-opening and overlap checks. Opening widths, confirmed adjacency, drift correction and benchmark accuracy remain unfinished.
