# Region-reviewed partial structural evidence

This CPU stage reviews **image regions**, restricts geometry to their existing accepted RGB stereo samples, and projects supported wall spans into a local floor coordinate system. It preserves source poses, estimated metre scale and missing coverage. It does not close a room, snap walls to right angles, calculate room area or certify physical dimensions. [Surface evidence](SURFACES.md), [grounding investigation](GROUNDING_DIAGNOSTICS.md), [staged structural plan](GROUNDING_PLAN.md).

## Native workflow

Install the existing optional runtime with uv; keep the web extra if the same venv also serves Holo:

```shell
uv sync --locked --extra web --extra reconstruct
cozmo-boundaries outputs/single-room-surfaces-v2 outputs/my-partial-review --sparse outputs/single-room-sparse-100-v2 --prepared outputs/single-room-preprocessing-final --bundle outputs/single-room-cli-v2 --dense outputs/linux-reconstruction/single-room-dense-100-v1 --source ../test_data/iphn-17/single_room
```

Without `--review`, the result supplies a source-bound empty `review.json` and reports insufficient structural evidence. No semantic decision is guessed. Copy that JSON to a separate file and populate its `regions` with reviewed polygons in **dense image-edge coordinates**, pixel centers `x+0.5,y+0.5`. Keep the source hashes and view identity fields from `views.json`; do not rotate coordinates. Each region names a source plane, rank, role (`FLOOR`, `WALL`, `FURNITURE`, `MIXED`, `UNKNOWN`), reason and convex polygon. Set `floor_plane_id` only for an explicitly reviewed horizontal floor candidate. Review authority is either assistant or user; an assistant declaration cannot claim human confirmation.

Then add `--review path/to/regions.json` and use a new output folder. Source-boundary ancestors/descendants and existing results are rejected. `--grounding path/to/report` optionally binds and audits the grounding result for status/provenance only; its object geometry, dimensions and thickness do not enter boundary geometry. Include the same option when creating the review identity and running/verifying the output.

```shell
python -m http.server 8005 --bind 127.0.0.1 --directory outputs/my-partial-review
```

Open http://127.0.0.1:8005/. The local page provides SVG export, floor/wall visibility controls, span tooltips and source-linked region images. Reports and the exact original/canonical review files are separate artifacts; editing one invalidates its hashes. Re-run with a separate revised input to update a result. Holo now displays published geometry through [its reconstruction tab](RECONSTRUCTION_VIEWER.md); HTTP reconstruction execution jobs remain subsequent integration.

## Docker workflow

The existing pinned CPU reconstruction runtime provides this stage without CUDA or a new library:

```shell
docker build --target boundaries -t holo-boundaries:0.2.0 .
docker run --rm --mount "type=bind,source=C:/Shrey_Projs/Recruitements_comp/tkh_cozmo,target=/workspace,readonly" --mount "type=bind,source=C:/Shrey_Projs/Recruitements_comp/tkh_cozmo/proto-2/outputs/linux-reconstruction,target=/results" holo-boundaries:0.2.0 /workspace/proto-2/outputs/single-room-surfaces-v2 /results/my-partial-review --sparse /workspace/proto-2/outputs/single-room-sparse-100-v2 --prepared /workspace/proto-2/outputs/single-room-preprocessing-final --bundle /workspace/proto-2/outputs/single-room-cli-v2 --dense /workspace/proto-2/outputs/linux-reconstruction/single-room-dense-100-v1 --source /workspace/test_data/iphn-17/single_room
```

Replace host paths with your own. Raw/source inputs mount read-only; a separate result location is writable. This does not rebuild/restart Holo or remove its captures volume. Append `--verify-only` with the same upstream/optional grounding paths to audit a published result. The archived review supports verification without its original external path.

## Geometry contract

- Full ingestion/prepared/sparse/dense/surface verification remains mandatory. Optional grounding adds its full-chain verifier and source/configuration identity. Frame/time, RGB grid/hash, original evidence-overlay hash and sampled-observation hash bind every reviewed region.
- Regions classify only accepted sampled pixels assigned to their named plane. Pixels are tested at their actual image-edge centers. Rejections override overlapping architectural marks; furniture wins over mixed, mixed over unknown. Unmarked pixels remain unreviewed. A wall region never certifies its whole plane or other frames. Polygon boundary coverage follows the point-set distinction documented by [Shapely](https://shapely.readthedocs.io/en/stable/reference/shapely.covers.html); the implementation uses a NumPy convex-perimeter test without adding Shapely.
- At least three reviewed views with eight samples per view and at least 15 cm source camera-center separation are needed for a floor/wall group. Repeated poses do not supply a baseline. These are engineering support requirements, not independent accuracy guarantees.
- The local floor frame uses the existing reviewed horizontal plane, +Y-oriented normal, projected world-X tangent, right-handed second tangent and the projected reviewed-point centroid as origin. Both 4×4 transforms are exported. It is a floor **hypothesis**, not a surveyed room datum.
- Floor evidence remains occupied 15 cm cells with at least two qualifying views and 15 cm baseline per cell. Empty or weak cells stay absent. This is local evidence coverage, not a room footprint or measured area.
- Wall–floor plane intersection uses the original plane equations via a [linear solve](https://numpy.org/doc/stable/reference/generated/numpy.linalg.solve). Wall observations supply extent along that line. Fifteen-centimetre bins require three qualifying views and 15 cm baseline each; only adjacent supported bins join. Endpoints use observed projected extent, minimum span 30 cm. Absent/weak bins are not bridged, and endpoints are not extended to guessed corners.
- Wall observations above the floor are projected to the floor line; height ranges and near-floor counts stay explicit. A projected span does **not** prove the actual floor–wall junction. No unseen junction, door, corner, perpendicularity, closed polygon or room area is inferred.

## Modules, artifacts and verification

[Module ownership](src/cozmo_reconstruction/boundaries/README.md) separates frozen request/policy, review admission, geometry, evidence analysis, presentation, coordination, verification and CLI. Existing NumPy/OpenCV suffice; there is no new dependency.

`manifest.json` binds the complete chain, policy, original review SHA, source fingerprint and all artifacts. `review.json` and `review_input.json` retain canonical and exact original review bytes. `views.json` binds grids/images/observations/frame/time. `reviewed_observations.npz` stores original sample index, rank, x/y, plane/role/region index and recomputed source-world xyz for every classified sample. `report.json` stores counts, floor frame/cells, supported wall intervals, gaps and unresolved states. Native RGB, original surface overlays and new region overlays remain distinct. `plan.svg`, `preview.png` and `index.html` provide inspectable projections.

Before atomic publication the verifier reaudits all upstream geometry, parses the archived review, recomputes classifications/xyz/frame/cells/spans/report, compares integer/category decisions exactly and permits only tiny numerical roundoff. Rehashed invented polygons or altered observation arrays fail. Copied RGB/evidence images must match their source hashes. Failed staging results are retained as diagnostics.

## Current single-room trial

The development review uses 45 source-bound assistant regions. P02 supplies local opening-floor evidence with the notebook excluded. P07 supplies a limited poster-wall region; its curtain/window pixels remain unknown. Other candidates overlap bed, desk, chair, window/curtains or ambiguous edges and are withheld. The blue patterned P05 surface remains unresolved pending user identification. No architectural identity is human certified.

Published `outputs/single-room-boundaries-v1` passes the complete native source/geometry audit with 81 hashed artifacts. It retains 11 supported P02 floor cells from three views with a 0.449 m camera baseline and one P07 projected span of approximately 0.599 source-estimated m from three views with a 1.847 m baseline. The wall points are approximately 0.649–1.753 m above the local floor hypothesis; **zero near-floor samples** establish a junction. The span is observed projected patch extent, not measured wall length. Room polygon, area and verified dimensions remain absent.

The full suite passes 99 cases on Windows and Linux; Ruff passes with 120 Python files already formatted. The native trial preserved all 1,420 protected source, upstream, prior grounding and original input file hashes. These audits establish lineage and implementation behavior, not physical accuracy. Private evidence and machine paths are excluded from wheel/source distributions. [Behavioral tests](tests/README.md).

The next stage is to resolve remaining architectural identities/coverage and obtain additional supported wall spans before attempting room topology. The double-room pose-transition issue and reconstruction/stitching remain subsequent work. Reference calibration still fails its separate residual check, so no verified room dimensions or scale correction are justified.

Linux whole-workspace-readonly verification also passes for all 81 published artifacts using the archived review. Subsequent [Holo plan/3D presentation](RECONSTRUCTION_VIEWER.md) now displays this evidence alongside the existing dense RGB result; it does not change structural acceptance or upstream geometry.
