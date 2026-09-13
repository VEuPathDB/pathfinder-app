FROM ghcr.io/astral-sh/uv:0.12.10 AS uv

FROM python:3.14-slim

COPY --from=uv /uv /uvx /usr/local/bin/

WORKDIR /app

# The lock names three repositories, so the install clones them.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Cached layer: dependencies. Only the manifests below bust it, so the
# application source stays out of it.
COPY apps/api/pyproject.toml apps/api/
COPY apps/api/uv.lock apps/api/
COPY apps/api/config.toml apps/api/

# The cache mount keeps uv's download cache across builds, so a dependency
# change fetches only the new packages.
WORKDIR /app/apps/api
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_LINK_MODE=copy uv sync --frozen --no-install-project

# Fast layer: application code. Every code change re-runs it.

WORKDIR /app

COPY apps/api/alembic.ini apps/api/
COPY apps/api/alembic apps/api/alembic

# The tests carry large VCR cassettes, so the image does not keep them.
COPY apps/api/src/pathfinder apps/api/src/pathfinder
RUN rm -rf apps/api/src/pathfinder/tests

# The glob makes this copy a no-op when the file is absent.
COPY ollama_models.yam[l] ./

# Run from source inside the image. Avoid a second `uv sync` after copying app
# code: installing the editable project needs the Hatchling build backend, and
# build isolation may try to fetch it from PyPI during every code-layer rebuild.
ENV PYTHONPATH=/app/apps/api/src
ENV PYTHONUNBUFFERED=1
WORKDIR /app/apps/api

EXPOSE 8000

# The server binds before the warm-up finishes and loads a catalog on demand,
# so serving is what a compose dependent needs. /health/ready reports warm-up
# progress per subsystem.
HEALTHCHECK --interval=10s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD [".venv/bin/uvicorn", "pathfinder.main:app", "--host", "0.0.0.0", "--port", "8000"]
