# Python source

The reconstruction package also includes separate [image-region review and partial boundaries](cozmo_reconstruction/boundaries/README.md): source-bound polygon admission, sampled-pixel exclusions, a local floor frame, supported wall intervals and independent publication audits. [Commands and current partial result](../PARTIAL_BOUNDARIES.md). Missing coverage stays open and physical dimensions remain unverified.

The reconstruction package also includes the separate [grounding diagnostic](cozmo_reconstruction/grounding/README.md): source-bound corner editor, planar pose alternatives, unconstrained size checks and optional accepted-stereo/surface diagnostics. [Commands and current review-required result](../GROUNDING.md). Baseline scale remains unchanged.

The reconstruction package also includes the CPU [surface evidence stage](cozmo_reconstruction/surfaces/README.md): plane proposals, accepted-depth lineage, occupied patches and focused RGB overlays. [Commands and limits](../SURFACES.md). Semantic identities and dimensions remain unverified; it adds no new numerical dependency.

Four sibling packages separate source ingestion, derived preprocessing/reconstruction and the optional web application:

| Package | Responsibility | Start here |
|---|---|---|
| `cozmo_ingestion` | Validate source observations, publish canonical bundles and verify integrity | [Package guide](cozmo_ingestion/README.md) |
| `cozmo_preprocessing` | Select native-grid RGB views, check visual connections and retain exact source calibration, poses and IMU | [Preprocessing guide](cozmo_preprocessing/README.md) |
| `cozmo_reconstruction` | Fixed-camera sparse triangulation and RGB stereo depth, source/geometry verification and independent CLIs | [Reconstruction guide](cozmo_reconstruction/README.md) |
| `cozmo_web` | Accept uploads, manage isolated jobs, serve results and the compiled frontend | [Service guide](cozmo_web/README.md) |

The web package invokes ingestion and preprocessing; preprocessing consumes the verified ingestion reader. Neither processing package imports the web service or frontend. Ingestion has no third-party runtime dependencies. `uv sync --locked --extra preprocess` installs NumPy/OpenCV for CLI preprocessing; `--extra web` includes these plus API dependencies for the complete application. See [the preprocessing contract](../PREPROCESSING.md) for commands, admitted inputs and verification.

Reconstruction consumes audited ingestion/preprocessing through its own restricted prepared-input reader and runs PyCOLMAP in a bounded worker. `--extra reconstruct` installs this optional backend; it has no web dependency and Holo integration is deferred. [Contract and real Windows/Linux trials](../RECONSTRUCTION.md).

The [dense subpackage](cozmo_reconstruction/dense/README.md) consumes a verified sparse model, estimates RGB stereo Z in a separate CUDA worker and independently checks masks/clouds. [Dense setup/results](../DENSE_RECONSTRUCTION.md). CPU verification remains available natively; Linux CUDA inference uses the mutually exclusive `dense` extra. Learned-depth comparison is an offline experiment using separately pinned assets, not the default runtime.

Run commands from the [project root](../README.md), not this directory. uv installs these packages into the project's `.venv`. Use `cozmo_ingestion` imports for Python consumers; root scripts are compatibility wrappers.

The product is named **Holo**. Existing `cozmo_*` package and CLI identifiers are retained for compatibility. [Architecture and dependency boundaries](../ARCHITECTURE.md).
