# Portable reconstruction presentation

**6 October:** `route.py` identifies provisional scanning stays and revisits; `local_rooms.py`
derives per-region surfaces from original accepted stereo contributions; `roomwise_svg.py` publishes
common-coordinate evidence. Automatic multi-stay captures can publish explicitly partial room-wise
evidence without invented outlines or ceilings. Direct room connections need no corridor exit.
The actual two-room test still lacks enough wall support for completion; single-room fitting is
unchanged. [Design, limits and replay](../../../docs/reconstruction/ROOMWISE_PLAN.md).

**Current automatic workflow (2026-10-04):** `dense_automatic.py` audits dense/surface outputs, selects an unconfirmed broad floor plane below cameras, computes height-persistent source-aligned spans through `structure.py`, completes those supported spans with the rectangle prior and independently estimates a ceiling upper envelope. Raw projected intervals remain diagnostic only; insufficient support fails with `DENSE_ROOM_SUPPORT_INSUFFICIENT`. `automatic.py` shares atomic nine-asset encoding and retains the labelled CPU sparse preview. Source poses/scale remain unchanged; no human furniture labels or measured ceiling are transferred. [Policy and limits](../../../AUTOMATIC_RECONSTRUCTION.md), [regression correction](../../../NATIVE_FLOOR_PLAN_FIX.md).


`export.py` audits the existing boundary chain, derives rigid floor display coordinates, a bounded deterministic RGB point subset, gap-preserving provisional plane intervals and unfilled plan occupancy. It publishes eight hash-bound assets atomically to a new directory and rechecks parent artifacts. `cli.py` owns portable arguments through `cozmo-publish-reconstruction`. Existing geometry is immutable; scale, poses and semantic acceptance are unchanged.

The scene documents display sampling, coordinate transform, camera path and reviewed evidence. Browser positions are little-endian float32 Nx3; colours are uint8 RGB Nx3. PLY is a binary display subset. Geometry engines remain offline; [the HTTP catalog](../../cozmo_web/README.md) only reads these bounded artifacts. [Workflow, interpretation and evidence](../../../docs/reconstruction/RECONSTRUCTION_VIEWER.md).

`structure.py` owns fixed CPU height-persistence filtering and bounded Huber line suggestions. `export.py` includes its diagnostics as an optional plan layer without changing source points or reviewed acceptance. [Floorplan refinement](../../../docs/reconstruction/FLOORPLAN_OPTIMIZATION.md).


`rough_room.py` adds opt-in complete rectangular hypotheses with assumed entry symbols and separately displayed ceiling references. Use `--rough-room` and optionally `--ceiling-reference`. Completion is separate from source-bound reviewed walls; no source scale correction occurs. Nine assets are published for this mode, including the downloadable complete SVG. [Design and commands](../../../docs/reconstruction/FLOORPLAN_OPTIMIZATION.md).


`ceiling.py` owns the provisional spatial upper-envelope diagnostic; the external ceiling reference is not its input. `objects.py` binds assistant RGB polygons to camera/image identities and visible existing voxels, with explicit minimum-footprint priors. `--object-review` adds approximate footprints. SVG and 3D Top use matching upward floor-v display coordinates. [Details](../../../docs/reconstruction/FLOORPLAN_OPTIMIZATION.md).
