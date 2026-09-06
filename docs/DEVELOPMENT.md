# Development Guide

The gates are defined twice, and both definitions are executable:
`.pre-commit-config.yaml` (local, on commit and on push) and
`.github/workflows/ci.yml` (CI). Read those two files for the current list;
this guide states only what a human types by hand and where the enforcement
lives. A table here would be a third copy, and it would be the wrong one.

`docs/knowledge/conventions/verification-gates.md` explains what each gate is
for.

## Install the hooks

Once after cloning:

```bash
cd apps/api
uv sync
cd ../..
yarn install
uv run pre-commit install --hook-type pre-commit --hook-type pre-push
```

`uv run pre-commit run --all-files` runs every commit-stage hook over the whole
tree; add `--hook-stage pre-push` for the push-stage ones.

## The commands

### API (Python)

```bash
cd apps/api

uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pyright src/pathfinder
uv run lint-imports
uv run vulture
uv run python scripts/check_max_lines.py
uv run python scripts/check_weak_assertions.py
uv run python -m pathfinder.devtools.openapi check
uv run pip-audit
uv run sphinx-build -b html docs docs/_build/html  # the CI build-docs job

uv run pytest src/pathfinder/tests/unit/ -v
uv run pytest src/pathfinder/tests/ -v          # adds the integration tier; needs Docker
uv run pytest --cov=src/pathfinder --cov-report=term-missing
```

### Web (TypeScript)

```bash
cd apps/web

yarn lint
yarn format:check
yarn typecheck
yarn check:boundaries
yarn check:weak-assertions
yarn check:strict-mode
yarn test
NEXT_PUBLIC_API_URL=http://localhost:8000 yarn build
yarn test:e2e              # needs the API, the worker and the web app running
```

### Packages

```bash
cd assistant-platform/packages/assistant-core      && uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy --strict src && uv run pytest
cd assistant-platform/packages/assistant-client-ts && yarn lint && yarn typecheck && yarn format:check && yarn test && yarn build
cd assistant-platform/packages/mcp-conformance     && uv run ruff check src tests && uv run mypy --strict src && uv run pytest
cd veupathdb-py                                    && uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy --strict src && uv run pytest tests/unit
cd veupathdb-mcp                                   && uv run ruff check src tests && uv run ruff format --check src tests && uv run mypy --strict src && uv run pytest tests/unit && uv run pytest tests/integration
```

`assistant-core`'s suite has an integration tier that starts Postgres through
testcontainers, so the bare `uv run pytest` needs Docker. `uv run pytest tests/unit`
is the hermetic run. `veupathdb-mcp`'s index tier starts a pgvector container and
runs that package's own alembic chain on it. All three run with no `pathfinder`
installed, which is the point: a distribution must not have grown a dependency on
the app.

The api runs both alembic chains at startup. A database an earlier PathFinder
built already holds `embedding_vectors` and `embedding_index_entries` under
PathFinder's chain, so the api exits with `DuplicateTableError` until the MCP
chain is stamped once on that database, from the `veupathdb-mcp` folder or the
`wdk-mcp` container: `alembic -c alembic.ini stamp head`. The dev volume and the
e2e volume (`pathfinder_test`) are such databases; a fresh one needs nothing.

### The bundle

```bash
node scripts/check-knowledge.mjs
node scripts/check-wdk-rules.mjs
node --test scripts/check-knowledge.test.mjs   # the checkers have their own tests
node --test scripts/check-wdk-rules.test.mjs
```

### Types

Backend Pydantic is the source of truth. After a schema change:

```bash
yarn generate:types
```

CI checks the result rather than writing it
(`uv run python -m pathfinder.devtools.openapi check`,
`yarn --cwd packages/shared-ts check:generated`), so a stale spec fails the
build instead of being rewritten inside someone's commit.

### Docker

```bash
docker compose --env-file .env.dev up -d --build --force-recreate api worker wdk-mcp web
docker compose exec api uv run pytest src/pathfinder/tests/ -v
```

## Architectural enforcement

Three checks enforce structure beyond linting.

**File size cap.** `apps/api/scripts/check_max_lines.py` fails when a Python
source file under `apps/api/src/pathfinder` or
`assistant-platform/packages/assistant-core/src/assistant_core` exceeds 400 meaningful lines,
counting neither blanks nor comments. Devtools and two declared pure-model
modules are exempt; the exemption set is in the script. Tests obey the cap:
`src/pathfinder/tests/.max-lines-baseline.txt` ratchets the files that were
already over it, and a baselined file fails as soon as it grows past its
recorded count. Run `--write-baseline` only to regenerate the whole list.

**Import linter.** `[tool.importlinter]` in `apps/api/pyproject.toml` holds the
seven backend layer contracts. `uv run lint-imports` reports which one broke.

**Boundary checker.** `apps/web/scripts/check-boundaries.mjs` refuses an import
from one feature into another. Exemptions live in the script.

## Security scanning

`.github/workflows/security.yml` runs on push and pull request to `main`, and
weekly:

- Trivy for known CVEs in dependencies (CRITICAL and HIGH)
- TruffleHog for verified secrets in history
- CodeQL for Python and JavaScript static analysis

`pip-audit` runs locally as a push-stage hook.
