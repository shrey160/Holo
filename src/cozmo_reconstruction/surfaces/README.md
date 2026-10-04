# Surface evidence modules

This CPU stage consumes independently verified dense RGB geometry. [Commands, contract and findings](../../../SURFACES.md). It is separate from Holo routes and future floorplan inference.

| Module | Ownership |
|---|---|
| `models.py` | Frozen request and bounded geometric/evidence policy |
| `geometry.py` | Seeded plane proposal/refinement, nearest assignments and occupied connected patches |
| `analysis.py` | Accepted-depth backprojection, sampled provenance, evidence and unconfirmed role hypotheses |
| `presentation.py` | Source-axis preview and offline per-candidate RGB review |
| `pipeline.py` | Full source audit, overlap guard, independent recomputation and transactional publication |
| `cli.py` | Native/container arguments and stable errors |

Keep mathematics independent of display and semantic decisions. Never treat the largest horizontal plane as a floor, or a supported vertical plane as a wall without image evidence. Do not fill unoccupied patches or change source poses/scale. Add behavioral fixtures for changed thresholds or conventions; upstream verification must stay mandatory.
