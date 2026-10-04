FROM python:3.10-slim-bookworm@sha256:f8aa74bffbe59d02f7442dba43c9ea72b2c34cc29aa7a7edc74b29521b23bb43
COPY --from=ghcr.io/astral-sh/uv:0.12.1@sha256:cf4eedcaa81655197f625739489effcbe71b61ceb1506f332c3facae5deceded /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /worker
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev
COPY worker.py probe.py ./
ENTRYPOINT ["/worker/.venv/bin/python", "worker.py"]
