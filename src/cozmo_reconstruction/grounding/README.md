# Grounding diagnostic modules

Read [the contract, commands and findings](../../../docs/grounding/GROUNDING.md). This stage is independent of Holo routes and floorplan inference. Baseline RGB geometry stays unchanged.

| Module | Ownership |
|---|---|
| `models.py` | Frozen requests and bounded diagnostic policy |
| `annotations.py` | Mandatory source audits, opening-frame association, native coordinates and corner provenance |
| `geometry.py` | Planar pose alternatives, independent corner triangulation and size/plane metrics |
| `confirmation.py` | Exact proposal/video/rank review binding and conditional thickness interval propagation |
| `diagnostics.py` | Controlled object-pose refinement, pixel-center hypotheses, holdouts and fixed-camera point fitting |
| `analysis.py` | Acceptance states, stationary pose spread, sensitivity and optional accepted-stereo/surface comparisons |
| `presentation.py` | Offline editor, coordinate mapping, local import/export and residual overlays |
| `pipeline.py` | Source/output guards, exact input archive and atomic publication |
| `verification.py` | Source/camera/reference/corner bindings and independent report recomputation |
| `cli.py` | Native/container entry point and stable errors |

Keep human marks and semantic decisions out of source ingestion and raw files. Declared size is a PnP input, so use unconstrained triangulation for a separate size diagnostic. Never turn a local reference ratio into automatic rescaling. Preserve missing support, planar ambiguity and unknown book thickness. Synthetic tests verify these behaviors; physical room accuracy requires independent measurements.

Reviewed v2 reports archive a separate confirmation record and add [controlled mismatch checks](../../../docs/grounding/GROUNDING_DIAGNOSTICS.md). Recompute archived review/interval/experiment data during verification. Historical v1 reports retain their original interpretation. Refined object poses/points never change camera poses or bypass the acceptance state.
