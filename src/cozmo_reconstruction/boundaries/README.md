# Partial-boundary modules

[Workflow and contract](../../../PARTIAL_BOUNDARIES.md). This CPU stage consumes reviewed image regions from an independently verified surface chain; it does not infer a closed room.

| Module | Responsibility |
|---|---|
| `models.py` | Frozen source request and bounded support policy |
| `reviews.py` | Full-chain audits, source/image/sample hashes, region roles and review provenance |
| `geometry.py` | Convex pixel coverage, reversible local floor frame, plane intersections, supported cells/bins and gap-preserving spans |
| `analysis.py` | Rejection precedence, accepted-sample lineage, region-only semantics and conditional partial projection |
| `presentation.py` | Offline SVG/PNG preview, source/region overlays and image-linked review |
| `pipeline.py` | Raw/upstream/review overlap guard, exact input archive and atomic publication |
| `verification.py` | Independent source/array/report recomputation and copied-image checks |
| `cli.py` | Native/container arguments and stable errors |

Keep review decisions separate from source ingestion and existing geometry. A wall region does not promote the entire plane; a local floor patch does not establish room area. Never bridge missing bins, extend corners, snap angles, change source poses/scale or apply unresolved grounding measurements. Assistant review is explicitly distinct from human architectural confirmation. Analytic fixtures test these boundaries; independent physical accuracy remains unverified.
