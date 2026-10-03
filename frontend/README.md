# Holo frontend

React/TypeScript/Vite UI with two tabs: **Capture guide** and **Input & validation**. It uses relative `/api` requests so the same build works with the native API and the single Docker application. Product branding is Holo; the existing private npm package identifier remains `cozmo-capture-ui`.

Verified Sensor Recorder results expose **Prepare reconstruction views**. This creates a separate queued history run and renders the [preprocessing review](src/features/preprocessing/README.md): selected thumbnails, pagination, weak-link/motion findings and a downloadable report. LiDAR and grounding measurements are excluded from processing; the original capture and optional reference attachments remain archived. [Processing contract](../PREPROCESSING.md).

## Native development

Use Node 24 LTS/npm. From `proto-2`, start Python in one terminal:

```shell
uv sync --locked --extra web
uv run --locked --extra web cozmo-web --reload
```

From this `frontend` directory, in a second terminal:

```shell
npm ci
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to `http://127.0.0.1:8000`. If Docker already owns port 8000, stop it or start Python with `--port 8001` and set `API_TARGET=http://127.0.0.1:8001` before starting Vite. In PowerShell: `$env:API_TARGET='http://127.0.0.1:8001'`.

The API needs FFmpeg/FFprobe. If absent from PATH, pass the actual FFmpeg path with the server's `--ffmpeg` option. [Complete setup and configuration](../WEB_SETUP.md).

## Build and editing

```shell
npm run build
npm run format:check
```

Build performs TypeScript checking and writes `dist/`. From `proto-2`, `uv run --locked --extra web cozmo-web` detects that build and serves it at port 8000. Docker builds these assets automatically; Node is not required in the running container. `npm run preview` previews static assets only and has no configured API proxy; use compiled native mode for the complete application.

| Location | Responsibility |
|---|---|
| [src/](src/README.md) | Entry points, layout, shared styles and feature composition |
| [src/features/guide/](src/features/guide/README.md) | Capture protocol cards and route diagram |
| [src/features/ingestion/](src/features/ingestion/README.md) | Upload form, job history, polling and verified results |
| [src/api/](src/api/README.md) | Shared types, requests, upload progress and downloads |
| [src/components/](src/components/README.md) | Shared Markdown renderer |
| `index.html` | Document title and HTML shell |
| `vite.config.ts` | React plugin, parent guide-file access, development port and API proxy |
| `package-lock.json` | npm dependency resolution; use `npm ci` |

Edit [capture.md](../capture.md) for protocol/settings content; it is imported at build time. Rebuild compiled native/Docker assets after changing it. Do not maintain a second independent copy of the guide. `node_modules/` and `dist/` are generated and ignored.
