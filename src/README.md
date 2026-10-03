# Python source

Two sibling packages separate ingestion from the optional web application:

| Package | Responsibility | Start here |
|---|---|---|
| `cozmo_ingestion` | Validate source observations, publish canonical bundles and verify integrity | [Package guide](cozmo_ingestion/README.md) |
| `cozmo_web` | Accept uploads, manage isolated jobs, serve results and the compiled frontend | [Service guide](cozmo_web/README.md) |

The web package imports the ingestion package. The ingestion package does not import FastAPI, the web service or the frontend. Its default runtime has no third-party Python dependencies; web dependencies are installed with `uv sync --locked --extra web`.

Run commands from the [project root](../README.md), not this directory. uv installs these packages into the project's `.venv`. Use `cozmo_ingestion` imports for Python consumers; root scripts are compatibility wrappers.

The product is named **Holo**. Existing `cozmo_*` package and CLI identifiers are retained for compatibility. [Architecture and dependency boundaries](../ARCHITECTURE.md).
