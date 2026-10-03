# Python source

Three sibling packages separate source ingestion, derived preprocessing and the optional web application:

| Package | Responsibility | Start here |
|---|---|---|
| `cozmo_ingestion` | Validate source observations, publish canonical bundles and verify integrity | [Package guide](cozmo_ingestion/README.md) |
| `cozmo_preprocessing` | Select native-grid RGB views, check visual connections and retain exact source calibration, poses and IMU | [Preprocessing guide](cozmo_preprocessing/README.md) |
| `cozmo_web` | Accept uploads, manage isolated jobs, serve results and the compiled frontend | [Service guide](cozmo_web/README.md) |

The web package invokes ingestion and preprocessing; preprocessing consumes the verified ingestion reader. Neither processing package imports the web service or frontend. Ingestion has no third-party runtime dependencies. `uv sync --locked --extra preprocess` installs NumPy/OpenCV for CLI preprocessing; `--extra web` includes these plus API dependencies for the complete application. See [the preprocessing contract](../PREPROCESSING.md) for commands, admitted inputs and verification.

Run commands from the [project root](../README.md), not this directory. uv installs these packages into the project's `.venv`. Use `cozmo_ingestion` imports for Python consumers; root scripts are compatibility wrappers.

The product is named **Holo**. Existing `cozmo_*` package and CLI identifiers are retained for compatibility. [Architecture and dependency boundaries](../ARCHITECTURE.md).
