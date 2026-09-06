## Pathfinder API (`apps/api`)

FastAPI backend for PathFinder. It owns the HTTP surface, the agents, the WDK client, the
services behind them, and the procrastinate worker that runs every chat turn.

### Key entrypoints

- **App**: `src/pathfinder/main.py`
- **Chat endpoint**: `src/pathfinder/transport/http/routers/chat.py` (`POST /api/v1/chat`)
- **Dispatcher** (persists the message, defers the turn, tails the log): `src/pathfinder/ai/conversation/dispatcher.py`
- **Turn runner** (worker side): `src/pathfinder/jobs/impls/chat_turn_impl.py` -> `src/pathfinder/ai/conversation/turn_runner.py`
- **Graph**: `src/pathfinder/ai/graph/builder.py` (`lead` -> `finalize_turn`)
- **Lead agent + ledger**: `src/pathfinder/ai/lead/lead_agent.py`, `src/pathfinder/ai/lead/ledger.py`
- **Worker**: `python -m pathfinder.jobs.worker` (`src/pathfinder/jobs/worker.py`)
- **MCP server**: `python -m veupathdb_mcp` (the `veupathdb-mcp` sibling distribution)

### Package structure

```
src/pathfinder/
  main.py                    # FastAPI app factory
  assistants/                # Composition root: one spec per assistant, plus the registry
    pathfinder_spec.py       #   The Lead + ledger assistant
    site_help/               #   A single-agent assistant: two catalog tools, no ledger
  ai/                        # The agents themselves
    agents/                  #   Sub-agent roles (frame, execution, verification), instructions,
                             #     history compaction, tool and parameter vocabulary
    capabilities/            #   PIGuard, error classification, resilience, security
    conversation/            #   Dispatcher, turn runner, assistant routing, request body,
                             #     title generator, turn stop
    graph/                   #   The two-node LangGraph: state, runtime, builder, lead_node,
                             #     nodes, stream events, lead-turn helpers
    lead/                    #   Lead agent, InvestigationLedger, sub-agent dispatch and tools,
                             #     case memory, intent gate, ledger rendering
    models/                  #   Model catalog, tiers, per-provider settings, mock/
    prompts/                 #   Prompt templates and loader
    scratchpad/              #   Scratchpad tools, toolset, rendering, compactor
    tools/                   #   standalone/ (one module per tool family), toolsets/ (what each
                             #     role mounts), durable.py (@durable_tool)
    strategy_stream_parts.py eda_stream_parts.py stream_part_payloads.py   # The data-* parts PathFinder emits and their payloads
    pricing.py               #   Per-1M-token price lookups for the Engine UI
  data/seeds/                # Per-site experiment seed JSON
  domain/                    # Pure domain logic this app owns (no I/O); the WDK-shaped half is veupathdb.domain
    conversation.py          #   Thread-level defaults the persistence layer and the services share
    eda.py eda_compute_config.py eda_parts.py eda_thread.py   # EDA predicates, compute-config checks, parts, thread state
    research/                #   Citation extraction and research helpers
    scratchpad/              #   Scratchpad note model
    strategy/                #   Diffing, hydration, revision, staleness, validation
  evals/                     # Eval case and extract shapes, redaction, scoring, summary
    corpus/                  #   One JSON per pinned case
  jobs/                      # Procrastinate worker: app, tasks, registry, runner, runtime,
                             #   impls/ (the real durable-tool bodies), progress, completion_turn
  persistence/               # Database layer
    models.py                #   Every table this app owns
    repositories/            #   SQLAlchemy repositories
  platform/                  # Shared infrastructure
    config.py                #   Settings (API keys, DB URL, feature flags)
    context.py               #   Request-scoped context variables
    errors.py                #   Error codes and exception types
    error_handlers.py        #   Every error rendered as problem+json
    health.py                #   Health check logic
    metrics.py               #   Application-level OTEL metric instruments
    migrations.py            #   Alembic upgrade to head at startup (both chains)
    notify_dispatcher.py     #   One LISTEN connection multiplexed over many subscribers
    observability.py         #   OTEL tracing, metrics, logs, library instrumentation
    langfuse/                #   Langfuse client, prompts, datasets, scoring
    principal.py             #   Who the caller is
    readiness.py             #   Readiness probe state
    security.py              #   Auth and authorization helpers
    store.py                 #   Cross-thread memory store wiring
    tasks.py                 #   Background task infrastructure
    tool_sources.py          #   Declared MCP tool sources
    uuid_utils.py            #   UUID formatting
  services/                  # Application services. The catalog, the WDK reads, gene lookup, the
                             #   control tests and the tool payloads are veupathdb_mcp, not here.
    control_sets.py          #   Control-set CRUD over the repository
    conversations/           #   Conversation lifecycle, fork, revert, cancellation, scratchpad
    eda/                     #   EDA study catalog, subsetting, compute, export
    enrichment/              #   Custom enrichment and its statistics
    eval.py                  #   Thesis evaluation: gold strategies and their gene ids
    eval_data/               #   Eval staging and promotion
    experiment/              #   Experiment engine (evaluate, persist, robustness, cross-validate,
                             #     enrich), sweeps, seeds, streaming
    export/                  #   Data export and its sweeper, incl. control downloads
    gene_sets/               #   Gene set CRUD, confidence, ensemble, enrichment
    parameter_optimization/  #   Parameter sweeps, scoring, builders
    quota.py                 #   Per-user monthly USD quota
    research/                #   Literature retrieval
    strategies/              #   Strategy lifecycle: build, commit, materialize, push, sync, revisions
    tasks/                   #   Background task rows and their queries
    user_data.py             #   Purges a user's data
    users.py                 #   User accounts
    wdk_identity.py          #   Who a request is on VEuPathDB, and the internal user it maps to
    workbench/               #   The facade ai/ and jobs/ reach the workbench through (gene_sets,
                             #     experiments, control_sets, comparisons, optimization); functions
                             #     with bodies, and the fifth import-linter contract forbids the rest
  transport/                 # HTTP layer
    http/
      routers/               #   FastAPI routers
        chat.py              #     Chat endpoint
        conversations/       #     CRUD, events, counts, fork, revert, WDK import, scratchpad
        sites/               #     Site-scoped catalog, gene, parameter endpoints
        experiments/         #     Experiment execution, evaluation, enrichment, results
        gene_sets/           #     Gene set CRUD, confidence, enrichment, records, operations
        control_sets.py      #     Control set CRUD
        eda.py               #     EDA studies, subset counts, distributions, viz
        evaluation.py        #     Thesis eval endpoints
        exports.py           #     Export download
        feedback.py          #     Product action feedback
        health.py            #     Health and readiness probes
        me.py                #     Privacy settings and quota
        memories.py          #     Cross-thread memory CRUD
        models.py            #     Model catalog
        tasks.py             #     Durable task list for a conversation
        tiers.py             #     Model tier catalog
        user_data.py         #     User data deletion
        veupathdb_auth.py    #     VEuPathDB auth proxy
        dev.py               #     Dev login (never written into the OpenAPI spec)
      schemas/               #   Pydantic request/response DTOs
      deps.py                #   FastAPI dependencies (auth, DB, site context)
      openapi.py             #   Spec post-passes
      sse_utils.py           #   SSE encoding helpers
  devtools/                  # Developer CLIs (chat debugger, evals desk, openapi, WDK fixtures)
  tests/                     # Unit + integration tests
```

### Architecture overview

**Request flow** (chat):

1. `POST /api/v1/chat` arrives at `transport/http/routers/chat.py`.
2. FastAPI dependencies (`deps.py`) inject the principal, a DB session and the site context.
3. `ai/conversation/dispatcher.py` resolves the thread's `AssistantSpec` from
   `conversations.assistant_id`, runs that assistant's identity gate, persists the user message,
   defers a `chat_turn` procrastinate job, and returns an SSE tail of the durable event log.
4. The worker picks the job up (`jobs/impls/chat_turn_impl.py`) and drives the spec's graph
   through `ai/conversation/turn_runner.py`. `AsyncPostgresSaver` checkpoints the turn.
5. Every chunk the graph emits is written to `conversation_events` and streamed to whoever is
   tailing the thread. A client that disconnects resumes from its cursor.
6. Tool calls mutate strategy state through `services/strategies/` and are pushed to WDK.

**The two assistants**:

`pathfinder` runs a Lead agent that is the only voice the user hears. It invokes FRAME, BUILD and
VERIFY sub-agents as tools and reads a typed `InvestigationLedger` they write. `site_help` runs one
agent with two catalog tools and no ledger, on the runtime's stock single-agent graph. Which
assistant a thread uses is fixed when the thread is created.

**Durable tools**:

`run_control_tests_on_step`, `optimize_search_parameters`, `run_gene_set_enrichment` and
`run_eda_compute` are deferred: the call creates a `background_tasks` row and a procrastinate job,
the turn ends, and the worker opens a new turn on the thread with the result once every task of
that step has reported.

**Persistence**:

- PostgreSQL via SQLAlchemy async sessions
- Repositories in `persistence/repositories/`; tables in `persistence/models.py`
- **Alembic** is the only path to the schema; `platform/migrations.py` upgrades to `head` at startup
- It runs two chains on the one connection: this app's, and `veupathdb_mcp`'s over the two
  embedding tables that distribution owns

**VEuPathDB integration**:

- `veupathdb.wdk` (the `veupathdb-py` sibling distribution) wraps the WDK REST API
- The strategy API client handles CRUD, step management and result reports
- The catalog, the WDK reads, gene lookup and the served MCP tools are `veupathdb_mcp`
  (the `veupathdb-mcp` sibling distribution), installed here and called in process
- Every WDK-backed feature needs a registered VEuPathDB login; guest calls are refused upstream

### Configuration

Settings are loaded from:

- **TOML**: `config.toml` (checked in; expected at `apps/api/config.toml`)
- **Environment**: `.env` (not checked in; see `/.env.example` at the repo root)

Common env vars:

- `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` if using those providers)
- `API_SECRET_KEY` (32+ chars; required in every profile)
- `DATABASE_URL` (required; no implicit localhost default)
- `PATHFINDER_CHAT_PROVIDER=default` for normal runs
- `PATHFINDER_CHAT_PROVIDER=mock` is allowed only in the dedicated test profile
- `DEFAULT_PROVIDER` and `DEFAULT_TIER` choose the base model preset when using real providers

### Run locally (no Docker)

Start Postgres:

```bash
docker compose --env-file .env.dev -f ../../docker-compose.yml -f ../../docker-compose.dev.yml up -d db
```

```bash
cd apps/api
cp ../../.env.dev.example .env
uv sync
uv run uvicorn pathfinder.main:app --reload --host 0.0.0.0 --port 8000
```

Chat turns run in the worker, so start it too or no turn will ever finish:

```bash
uv run python -m pathfinder.jobs.worker
```

API will be available at:

- `http://localhost:8000/health`
- `http://localhost:8000/docs` (when docs are enabled)

### Build Sphinx docs

```bash
cd apps/api
uv sync --group docs
uv run sphinx-build -b html docs docs/_build/html
```

Output: `docs/_build/html/`. Hosted at [veupathdb-pathfinder.readthedocs.io](https://veupathdb-pathfinder.readthedocs.io/).

### Run tests / lint / typecheck

The full gate list is in `docs/DEVELOPMENT.md`. The short form:

```bash
cd apps/api
uv run ruff check . && uv run ruff format --check .
uv run mypy src && uv run pyright src/pathfinder
uv run lint-imports
uv run pytest src/pathfinder/tests/unit/ -v
```
