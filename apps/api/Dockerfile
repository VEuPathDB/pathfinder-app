# Grab uv binary from the official image — avoids `pip install uv` bootstrap.
FROM ghcr.io/astral-sh/uv:latest AS uv

FROM python:3.14-slim

COPY --from=uv /uv /uvx /usr/local/bin/

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# ── Cached layer: dependencies + models (busted only by pyproject.toml/uv.lock) ──

# Copy dependency manifests only — NOT application source code.
COPY apps/api/pyproject.toml apps/api/
COPY apps/api/uv.lock apps/api/
COPY apps/api/config.toml apps/api/
COPY packages/assistant-core/pyproject.toml packages/assistant-core/
COPY packages/assistant-core/src packages/assistant-core/src
COPY packages/mcp-conformance/pyproject.toml packages/mcp-conformance/
COPY packages/mcp-conformance/README.md packages/mcp-conformance/
COPY packages/mcp-conformance/src packages/mcp-conformance/src

# Install dependencies without the project itself (no source code needed).
# Cache mount preserves uv's download cache across builds — even when deps
# change, already-fetched packages aren't re-downloaded from PyPI.
WORKDIR /app/apps/api
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_LINK_MODE=copy uv sync --frozen --no-install-project

# Download PIGuard ONNX model + tokenizer for prompt-injection detection.
# Cache mount on HF_HOME preserves the HuggingFace download across rebuilds;
# hf_hub_download copies files from the HF cache into /app/models/piguard,
# which is baked into the image layer.
ENV HF_HOME=/root/.cache/huggingface
RUN --mount=type=cache,target=/root/.cache/huggingface \
    .venv/bin/python <<'PYEOF'
from huggingface_hub import hf_hub_download
import os
model_dir = '/app/models/piguard'
os.makedirs(model_dir, exist_ok=True)
for fname in ('model.onnx', 'tokenizer.json'):
    hf_hub_download(
        repo_id='ahmedomuharram/piguard-onnx',
        filename=fname,
        local_dir=model_dir,
    )
print(f'PIGuard model downloaded to {model_dir}')
PYEOF

# Verify PIGuard loads correctly at build time.
RUN .venv/bin/python <<'PYEOF'
import onnxruntime
from tokenizers import Tokenizer
session = onnxruntime.InferenceSession('/app/models/piguard/model.onnx', providers=['CPUExecutionProvider'])
tokenizer = Tokenizer.from_file('/app/models/piguard/tokenizer.json')
print('PIGuard ONNX model verified')
PYEOF

# ── Fast layer: application code (re-runs on every code change, but cheap) ──

WORKDIR /app

# Copy Alembic config and migrations
COPY apps/api/alembic.ini apps/api/
COPY apps/api/alembic apps/api/alembic

# Copy application code (exclude tests — they add ~300MB of VCR cassettes)
COPY apps/api/src/data apps/api/src/data
COPY apps/api/src/pathfinder apps/api/src/pathfinder
RUN rm -rf apps/api/src/pathfinder/tests

# Copy optional Ollama models config (glob avoids failure if missing)
COPY ollama_models.yam[l] ./

# Run from source inside the image. Avoid a second `uv sync` after copying app
# code: installing the editable project needs the Hatchling build backend, and
# build isolation may try to fetch it from PyPI during every code-layer rebuild.
ENV PYTHONPATH=/app/apps/api/src:/app/packages/assistant-core/src
ENV PYTHONUNBUFFERED=1
WORKDIR /app/apps/api

# Expose port
EXPOSE 8000

# Health check — the server binds before the warm-up finishes and loads a
# catalog on demand, so serving is what a compose dependent needs. Warm-up
# progress is reported per subsystem by /health/ready, which the UI polls.
HEALTHCHECK --interval=10s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD [".venv/bin/uvicorn", "pathfinder.main:app", "--host", "0.0.0.0", "--port", "8000"]
