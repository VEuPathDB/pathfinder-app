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

# Cached layer: dependencies and models. Only the manifests below bust it, so
# the application source stays out of it.
COPY apps/api/pyproject.toml apps/api/
COPY apps/api/uv.lock apps/api/
COPY apps/api/config.toml apps/api/

# The cache mount keeps uv's download cache across builds, so a dependency
# change fetches only the new packages.
WORKDIR /app/apps/api
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_LINK_MODE=copy uv sync --frozen --no-install-project

# Download PIGuard ONNX model + tokenizer for prompt-injection detection.
# hf_hub_download fills the HF cache on the mount, so a later build finds the
# files there; the copy into /app/models/piguard is what the image layer keeps.
ENV HF_HOME=/root/.cache/huggingface
RUN --mount=type=cache,target=/root/.cache/huggingface \
    .venv/bin/python <<'PYEOF'
from huggingface_hub import hf_hub_download
import os
import shutil
model_dir = '/app/models/piguard'
os.makedirs(model_dir, exist_ok=True)
for fname in ('model.onnx', 'tokenizer.json'):
    cached = hf_hub_download(repo_id='ahmedomuharram/piguard-onnx', filename=fname)
    shutil.copyfile(cached, os.path.join(model_dir, fname))
print(f'PIGuard model copied to {model_dir}')
PYEOF

# Verify PIGuard loads correctly at build time.
RUN .venv/bin/python <<'PYEOF'
import onnxruntime
from tokenizers import Tokenizer
session = onnxruntime.InferenceSession('/app/models/piguard/model.onnx', providers=['CPUExecutionProvider'])
tokenizer = Tokenizer.from_file('/app/models/piguard/tokenizer.json')
print('PIGuard ONNX model verified')
PYEOF

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
