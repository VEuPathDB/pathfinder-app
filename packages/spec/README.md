## API spec -- `packages/spec`

This folder contains the OpenAPI specification for the Pathfinder API.

### Contents

- `openapi.json` and `openapi.yaml` -- the OpenAPI 3.x spec defining all HTTP endpoints, request/response schemas, and SSE event types

### Key API surface areas

78 operations over 68 paths, tagged as:

- **chat** (`/api/v1/chat`) -- one POST that opens a turn and returns an SSE tail
- **conversations** (`/api/v1/conversations/`) -- CRUD, the event log and its snapshot, counts, fork, revert, WDK import, saved-strategy insert, sidebar
- **scratchpad** -- the per-conversation scratchpad notes
- **tasks** (`/api/v1/conversations/{id}/tasks`) -- the durable task list of a conversation
- **sites** (`/api/v1/sites/`) -- VEuPathDB site catalog and search metadata, with sub-routes for catalog, genes and parameters
- **gene-sets** (`/api/v1/gene-sets/`) -- CRUD, confidence, enrichment, records, set operations
- **audits** (`/api/v1/audits/`) -- the current user's gene-model audit runs, one run, its findings and one finding with its evidence, and the words an audit page names each value by
- **eda** (`/api/v1/eda/`) -- study catalog, subset counts, distributions, visualizations
- **memories** (`/api/v1/memories`) -- cross-thread memory list, search, edit, delete
- **exports** (`/api/v1/exports/{id}`) -- export download
- **models** / **tiers** -- the LLM model catalog and its tier presets
- **me** (`/api/v1/me/`) -- privacy settings and quota
- **user** (`/api/v1/user/data`) -- user data deletion
- **product-events** (`/api/v1/product-events`) -- what a researcher did in the UI, recorded in Langfuse
- **eval** (`/api/v1/eval/`) -- thesis evaluation endpoints
- **veupathdb-auth** (`/api/v1/veupathdb/auth/`) -- VEuPathDB authentication proxy
- **health** (`/health`, `/health/ready`, `/health/config`, `/health/system`) -- probes

Dev-only routes (`/api/v1/dev/`) are refused by the generator rather than written, so they never
appear here.

### Update the OpenAPI spec

The backend Pydantic models are the source of truth. Regenerate after changing them:

```bash
cd apps/api
VEUPATHDB_SITES_CONFIG=../../deploy/sites/qa.yml DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/pathfinder uv run python -m pathfinder.devtools.openapi generate
```

The app is built in process and connects to nothing, so the database address is a
placeholder; settings refuse a process with no address.

CI and the pre-commit hook run `... openapi check` instead: it fails when the
committed spec is behind the app rather than rewriting it.

### Generate TypeScript types from the spec

The repo generates TS types from this spec into `packages/shared-ts/src/generated`.

```bash
yarn generate:types
```
