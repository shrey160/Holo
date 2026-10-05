# Two-room route review — 6 October 2026

This is a separate partial-evidence result following the [original failed two-room test](../two-room-2026-10-05/README.md). **Two scanning regions were identified, but neither room has a supported closed outline.** Do not count this as a two-room floor-plan pass.

The original source, sparse/dense/surface artifacts, failed job state and historical viewers remain unchanged. No measured dimensions, grounding correction or ceiling reference were used. The existing unconfirmed P06 floor display frame was retained.

[Machine-readable evidence](evidence.json), [room-wise evidence SVG](roomwise.svg), [implementation and replay command](../../reconstruction/ROOMWISE_PLAN.md).

The new Holo result is [two-room-route-review-20261006-v2](http://localhost:8000/?reconstruction=two-room-route-review-20261006-v2#reconstruction). It separates room-local spans and scanning trajectories from the unresolved connector; the common point cloud remains interactive. Both room cards explain missing wall support.

Verification: the full upstream chain was audited before and after publication; all nine derived assets passed hash checks; an independent deterministic local replay matched the published report; the raw ZIP hash remained unchanged. Full Windows regression suite: 198 tests passed. No fresh stereo, Docker or hardware accuracy benchmark was run.
