<div align="center">
  <h1>
    <img
      src="apps/web/public/pathfinder.svg"
      alt="PathFinder"
      height="32"
      style="vertical-align: middle; margin-right: 8px;"
    />
    PathFinder
  </h1>
  <p>An open-source tool-calling LLM agent for constructing VEuPathDB search strategies.</p>
  <p><strong><em>How Underspecified Prompts Shape Tool-Calling LLM Agents in Scientific Workflows</em></strong></p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.14%2B-3776AB?logo=python&logoColor=white" alt="Python 3.14+" />
    <img src="https://img.shields.io/badge/Node.js-24%2B-339933?logo=node.js&logoColor=white" alt="Node.js 24+" />
    <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
    <img src="https://img.shields.io/badge/Next.js-000000?logo=next.js&logoColor=white" alt="Next.js" />
    <img src="https://img.shields.io/badge/OpenAPI-6BA539?logo=openapi-initiative&logoColor=white" alt="OpenAPI" />
    <img src="https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white" alt="Docker" />
    <img src="https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL" />
<img src="https://img.shields.io/badge/OpenAI-412991?logo=openai&logoColor=white" alt="OpenAI" />
    <img src="https://img.shields.io/badge/Anthropic-191919?logo=anthropic&logoColor=white" alt="Anthropic" />
    <img src="https://img.shields.io/badge/Gemini-8E75B2?logo=google-gemini&logoColor=white" alt="Google Gemini" />
    <img src="https://img.shields.io/badge/Ollama-000000?logo=ollama&logoColor=white" alt="Ollama" />
  </p>
  <img src="assets/pathfinder.png" alt="PathFinder" width="100%" />  <p>
    <img src="https://img.shields.io/github/stars/ahmedOmuharram/pathfinder?style=social" alt="GitHub stars" />
  </p>

</div>

PathFinder's goal is to make complex query/strategy construction **easier, faster, and more reliable** by combining:

- **A Lead agent with specialist sub-agents** (the Lead is the only voice the user hears; it frames the problem, builds, and verifies through sub-agents it invokes as tools)
- **Execution with real tools** (build/edit a real strategy graph via validated tool calls)
- **Catalog grounding** (live WDK catalog for discovery and examples)

This project is intended to be integrated with **VEuPathDB systems** in the future once the research prototype is sufficiently mature.

## What's in this repo

This repo is organized as:

- **`apps/api/`**: FastAPI backend ("Pathfinder API")
  - Chat endpoint (`/api/v1/chat`) that defers the turn to the worker and returns an SSE tail of the durable event log.
  - The agents themselves, the WDK client, the services, and the procrastinate worker.
- **`apps/web/`**: Next.js UI
  - Chat UI with strategy graph visualization, step editing, and result panes.
  - **Workbench** for gene set management and multi-panel analysis (enrichment, distributions, cross-validation).
  - Proxies API routes via Next rewrites (see `apps/web/next.config.ts`).
- **`packages/assistant-core/`**: the assistant runtime (`assistant_core`), a distribution of its own that knows nothing about genes or strategies. `PROTOCOL.md` here is the wire protocol.
- **`packages/assistant-client-ts/`**: the headless TypeScript consumer of that protocol (`@pathfinder/assistant-client`). No React.
- **`packages/shared-ts/`**: shared TypeScript types (`@pathfinder/shared`) plus the Kubb-generated `src/generated/{types,zod,hooks}`.
  - The web app imports types via TS path mapping to `packages/shared-ts/src` (see `apps/web/tsconfig.json`).
- **`packages/mcp-conformance/`**: the conformance suite an MCP tool server passes before a deployment admits it.
- **`packages/spec/`**: OpenAPI spec (`packages/spec/openapi.json` and `.yaml`)

The API also includes: gene set management, an experiment engine (metrics, cross-validation, enrichment), export tools, a model catalog with token metrics, cross-thread memory, and an MCP server.

## How it works

### The Lead and its sub-agents

A turn runs a two-node LangGraph graph. The **Lead** agent is the only voice the user hears; it
invokes the specialists as tools and reads a typed ledger they write:

- **FRAME**: turn an underspecified request into a bound specification, using the live catalog and past cases
- **BUILD**: create and edit **strategy graph steps** through validated tool calls, against real WDK searches
- **VERIFY**: check what was built against what was asked, and report the difference

A second assistant, `site_help`, runs a single agent with two catalog tools and no ledger. Which
one a thread uses is fixed when the thread is created.

### Turns, the worker, and streaming

The API process never runs an agent. `POST /api/v1/chat` persists the user message, defers a
`chat_turn` job to the worker, and returns an SSE tail of the durable event log. The worker drives
the graph and writes every chunk to `conversation_events`; readers tail it over SSE, and a client
that disconnects resumes from its cursor. The wire format is the Vercel AI SDK v6 UI Message Stream.
Long-running tools (enrichment, control tests, parameter optimization, EDA compute) are deferred to
the worker as background tasks and answered on a later turn of the same thread.

Key entrypoints:

- API app: `apps/api/src/pathfinder/main.py`
- Chat route and dispatcher: `apps/api/src/pathfinder/transport/http/routers/chat.py`, `ai/conversation/dispatcher.py`
- Turn runner (worker side): `apps/api/src/pathfinder/jobs/impls/chat_turn_impl.py`, `ai/conversation/turn_runner.py`
- Graph and Lead: `apps/api/src/pathfinder/ai/graph/builder.py`, `ai/lead/lead_agent.py`
- Tools: `apps/api/src/pathfinder/ai/tools/` (`standalone/` definitions, `toolsets/` per role)
- Event log and SSE: `packages/assistant-core/src/assistant_core/conversation/{event_writer,event_stream}.py`

## Running locally

### Prerequisites

- **Docker** (recommended for Postgres and the full stack)
- **Python 3.14+**
- **Node.js 24+**

### Code quality (recommended)

Enable local formatting/linting hooks so issues are caught before push:

```bash
cd apps/api
uv sync
cd ../..
yarn install
uv run pre-commit install --hook-type pre-commit --hook-type pre-push
```

### Configuration

There are still two configuration sources for the API:

- **TOML**: `apps/api/config.toml` (checked in)
- **Environment**: `.env` / `.env.dev` (not checked in; examples exist)

The repo now ships with two explicit profiles:

- **Strict / production-style**
  - root env: [`.env.example`](.env.example)
  - compose: [`docker-compose.yml`](docker-compose.yml)
  - observability wiring: [`docker-compose.observability.yml`](docker-compose.observability.yml)
- **Local development**
  - root env: [`.env.dev.example`](.env.dev.example)
  - compose: [`docker-compose.dev.yml`](docker-compose.dev.yml)
  - observability stack: [`docker-compose.observability.dev.yml`](docker-compose.observability.dev.yml)

The base profile is intentionally fail-closed. PathFinder will not boot until you explicitly provide:

- `API_SECRET_KEY`
- `DATABASE_URL`
- `NEXT_PUBLIC_API_URL`
- `PATHFINDER_CHAT_PROVIDER=default`
- a real model backend (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, or `OLLAMA_BASE_URL`)

Those two files are the only env templates. A direct app run copies one of
them into the `.env` its process reads: the API reads `<repo>/.env` and
`apps/api/.env`, the web app reads `apps/web/.env`. The test profile is
generated on demand (see [Option C](#option-c-test--e2e-profile)).

### Local models (Ollama)

PathFinder supports local LLMs via [Ollama](https://ollama.com). To add local models:

1. Install and start Ollama (`ollama serve`).
2. Pull any models you want (e.g. `ollama pull qwen3:8b`).
3. Copy the example config and edit it:

```bash
cp ollama_models.yaml.example ollama_models.yaml
```

Each entry in `ollama_models.yaml` specifies:

| Field          | Required | Description                                            |
| -------------- | -------- | ------------------------------------------------------ |
| `model`        | yes      | Ollama model name (e.g. `qwen3:8b`, `llama3`)          |
| `name`         | no       | Display name in the UI (defaults to model name)        |
| `thinking`     | no       | Whether the model supports reasoning (default `false`) |
| `context_size` | no       | Max context window in tokens (default `4096`)          |

Example:

```yaml
models:
  - model: qwen3:8b
    name: Qwen 3 8B
    thinking: true
    context_size: 40960
  - model: llama3
    name: Llama 3
    context_size: 8192
```

When running the API inside Docker, set `OLLAMA_BASE_URL=http://host.docker.internal:11434/v1` in your `.env` so the container can reach Ollama on the host.

### Option A: strict/base Docker Compose

From repo root:

```bash
cp .env.example .env
# fill in .env with real values first
docker compose up --build
```

- Web: `http://localhost:3000`
- API: `http://localhost:8000`
  - Docs: `http://localhost:8000/docs`
  - Health: `http://localhost:8000/health`

Notes:

- This profile assumes you configured real infrastructure endpoints and a real model backend.
- The base compose file runs Postgres as the `db` service; there is no Redis in this stack.

### Option B: local development profile

From repo root:

```bash
cp .env.dev.example .env.dev
# fill in a real model backend before starting
docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml up --build
```

- Web: `http://localhost:3000`
- API: `http://localhost:8000`
- Postgres: `localhost:5432`

This is where local-only behavior lives: watch mode and the local Postgres container. Mock mode is not enabled here.

### Option C: test / E2E profile

From repo root:

```bash
cat > .env.test <<'EOF'
API_ENV=test
PATHFINDER_CHAT_PROVIDER=mock
NEXT_PUBLIC_API_URL=http://api:8000
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/pathfinder
DEFAULT_PROVIDER=anthropic
DEFAULT_TIER=balanced
EOF
printf 'API_SECRET_KEY=%s\n' "$(openssl rand -hex 32)" >> .env.test
docker compose --env-file .env.test -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.e2e.yml up -d --build --wait api worker web
```

This is the only Docker profile that enables `PATHFINDER_CHAT_PROVIDER=mock`.
The e2e overlay builds the web container's `runner` target, so port 3000 serves
the production build here as it does in CI: no development overlay over the
controls a spec clicks, and no per-route compile to grow the server's heap.

### Observability

PathFinder supports two observability modes:

- **SigNoz** - full-stack APM (distributed traces, metrics, logs). UI at `http://localhost:3301`
- **Langfuse** - LLM observability (prompt traces, token usage, cost tracking). UI at `http://localhost:3100`

PathFinder also ships a SigNoz pack for dashboards and alert intent:

- pack source: [`ops/observability/signoz/pathfinder-observability-pack.json`](ops/observability/signoz/pathfinder-observability-pack.json)
- generated dashboards and alert catalog: [`ops/observability/signoz/`](ops/observability/signoz)
- dashboard filter glossary: [`ops/observability/signoz/dashboard-filters.md`](ops/observability/signoz/dashboard-filters.md)

Refresh the generated artifacts with:

```bash
python3 ops/observability/signoz/render_pack.py
```

Import the generated dashboard JSON files into the SigNoz UI. The alert catalog stays environment-neutral so the same thresholds, labels, and runbooks can be used in local, staging, production, or Cedar-hosted workflows without depending on SigNoz-only routing details.

The local observability profile also provisions explicit UI credentials instead
of relying on ad hoc first-run setup:

- SigNoz admin user: `SIGNOZ_ROOT_USER_EMAIL` / `SIGNOZ_ROOT_USER_PASSWORD`
- Langfuse admin user: `LANGFUSE_INIT_USER_EMAIL` / `LANGFUSE_INIT_USER_PASSWORD`

To run a live end-to-end verification against the local stack after it starts:

```bash
python3 ops/observability/live_smoke_test.py
```

That smoke test drives one real chat turn through the local API and then checks
both Langfuse and SigNoz storage directly.

**Production/staging wiring**: point the API at existing observability backends.

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d
```

Set these explicitly in `.env` when using that overlay:

- `SIGNOZ_OTEL_ENDPOINT`
- `LANGFUSE_HOST`
- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`

**Local-development observability**: start a self-hosted Langfuse + SigNoz stack.

```bash
docker compose --env-file .env.dev \
 -f docker-compose.yml \
 -f docker-compose.dev.yml \
 -f docker-compose.observability.yml \
 -f docker-compose.observability.dev.yml \
  up -d
```

That dev overlay bootstraps a local Langfuse project. Open `http://localhost:3100` and sign in with:

```bash
email:    dev@pathfinder.local
password: pathfinder-local-dev
```

### Option D: run API + Web directly (no Docker)

API:

```bash
cd apps/api
cp ../../.env.dev.example .env
uv sync
uv run uvicorn pathfinder.main:app --reload --host 0.0.0.0 --port 8000
```

If you're not running the full stack via Docker Compose, start local services with the explicit dev overlay:

```bash
docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml up -d db
```

Web:

```bash
cd apps/web
cp ../../.env.dev.example .env
yarn install
yarn dev
```

## Testing, linting, and code quality

Quick reference - see **[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)** for the hooks, the CI pipelines, security scanning and architectural enforcement.

```bash
# API
cd apps/api
uv run ruff check .                  # Lint
uv run mypy src                      # Type check (mypy)
uv run pyright src/pathfinder        # Type check (pyright)
uv run lint-imports                  # Layering contracts
uv run pytest src/pathfinder/tests/ -v   # Tests

# Web
cd apps/web
yarn typecheck                       # tsc --noEmit
yarn lint                            # eslint
yarn check:boundaries                # Feature isolation
yarn test                            # Unit tests
yarn test:e2e                        # E2E tests
```

Pre-commit hooks enforce all of the above automatically - install with:

```bash
uv run pre-commit install --hook-type pre-commit --hook-type pre-push
```

## Documentation

**API docs:** [veupathdb-pathfinder.readthedocs.io](https://veupathdb-pathfinder.readthedocs.io/)

API documentation is built with **Sphinx** and covers architecture, agents, tools, and modules. A `.readthedocs.yaml` config is included for hosting on Read the Docs.

### Build locally

```bash
cd apps/api
uv sync --group docs
uv run sphinx-build -b html docs docs/_build/html
```

Open `apps/api/docs/_build/html/index.html` in a browser.

## OpenAPI + shared types

- OpenAPI spec: `packages/spec/openapi.json`
- Regenerate the spec and every generated TS artifact from the application itself
  (no container needs to be running, and a dev-only route is refused, not written):

```bash
yarn generate:types
```

The web app also uses path-based imports for shared TS types (see `apps/web/tsconfig.json`) and Next transpilation settings (`apps/web/next.config.ts`).

CI and the pre-commit hooks check the result rather than writing it, so a stale spec fails the build instead of being rewritten inside a commit.

## Roadmap / what's missing

PathFinder is a research-driven prototype. These are the biggest gaps you should expect today:

- **CD (deployment pipelines)**: CI (`.github/workflows/ci.yml`) and a security scan workflow exist, but there is no continuous deployment pipeline yet.
- **Contribution docs**: no `CONTRIBUTING.md`, no governance/release process.
- **Production hardening**: no documented deployment path (containers, reverse proxy, secrets management)
- **Database migrations**: Alembic is the only path to the schema, and the API migrates to `head` at startup (`platform/migrations.py`). There is no rollback story and no data-migration convention.
- **Evaluation** (thesis): an evaluation framework exists in `thesis/eval/` (gold strategies, prompts, analysis scripts), but reproducible experiment packaging and benchmarks are still in progress.

## Thesis context: "How Underspecified Prompts Shape Tool-Calling LLM Agents in Scientific Workflows"

PathFinder is built around the idea that ambiguous or underspecified requests are normal when humans describe complex strategies. The system therefore emphasizes:

- **integrated framing** (the Lead binds an underspecified request to a real specification before anything is built, and says what it assumed)
- **catalog grounding** (reduce hallucinated tool names/parameters)
- **validation and error shaping** (turn tool failures into actionable, structured feedback)
- **decomposition + delegation** (break complex goals into smaller strategy subproblems)

## Acknowledgements

PathFinder builds on:

- **VEuPathDB / WDK** concepts and APIs (strategy graphs, searches, parameter specs)
- **FastAPI** (API) and **Next.js** (web UI)
- **pydantic-ai** for tool-calling agents and **LangGraph** for the durable turn graph
