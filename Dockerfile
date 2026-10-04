# syntax=docker/dockerfile:1
FROM node:24.20.0-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
COPY capture.md /build/capture.md
RUN npm run build

FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS python-build
COPY --from=ghcr.io/astral-sh/uv:0.12.1@sha256:cf4eedcaa81655197f625739489effcbe71b61ceb1506f332c3facae5deceded /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0 UV_CACHE_DIR=/opt/uv-cache
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/opt/uv-cache uv sync --locked --extra web --extra reconstruct --no-dev --no-install-project
COPY src/ src/
RUN --mount=type=cache,target=/opt/uv-cache uv sync --locked --extra web --extra reconstruct --no-dev --no-editable

FROM python-build AS checks
COPY tests/ tests/
RUN --mount=type=cache,target=/opt/uv-cache uv sync --locked --extra web --extra reconstruct --no-editable
RUN .venv/bin/python -m unittest discover -s tests -v && .venv/bin/ruff check src tests

FROM python-build AS reconstruction
RUN --mount=type=cache,target=/opt/uv-cache uv sync --locked --extra reconstruct --no-dev --no-editable
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["cozmo-reconstruct"]

FROM reconstruction AS surfaces
ENTRYPOINT ["cozmo-surfaces"]

FROM reconstruction AS grounding
ENTRYPOINT ["cozmo-grounding"]

FROM reconstruction AS boundaries
ENTRYPOINT ["cozmo-boundaries"]

FROM reconstruction AS viewer
ENTRYPOINT ["cozmo-publish-reconstruction"]

# Separate environment: CPU and CUDA distributions expose the same Python module.
FROM python-build AS dense
RUN apt-get update && apt-get install -y --no-install-recommends libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/opt/uv-cache uv sync --locked --extra dense --no-dev --no-editable
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["cozmo-dense"]

FROM dense AS web-dense
RUN --mount=type=cache,target=/opt/uv-cache uv sync --locked --extra web --extra dense --no-dev --no-editable

FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir -p /data && chown app:app /data
WORKDIR /app
COPY --from=frontend /build/frontend/dist /app/static
ENV PATH="/app/.venv/bin:$PATH" DATA_ROOT=/data STATIC_ROOT=/app/static PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3)"
CMD ["cozmo-web", "--host", "0.0.0.0", "--port", "8000"]


FROM runtime AS gpu-app
COPY --from=web-dense /app/.venv /app/.venv

# Default portable CPU app. GPU users select gpu-app through compose.gpu.yaml.
FROM runtime AS app
COPY --from=python-build /app/.venv /app/.venv
