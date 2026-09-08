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
uv run --group docs sphinx-build -b html docs docs/_build/html  # the CI build-docs job

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

### The libraries

The three libraries are repositories of their own and run their own gates. Each
one's README states them; none of them runs from this checkout.

The api runs both alembic chains at startup. A database an earlier PathFinder
built already holds `embedding_vectors` and `embedding_index_entries` under
PathFinder's chain, so the api exits with `DuplicateTableError` until the MCP
chain is stamped once on that database, from a checkout of the MCP repository or
the `wdk-mcp` container: `alembic -c alembic.ini stamp head`. The dev volume and
the e2e volume (`pathfinder_test`) are such databases; a fresh one needs nothing.

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

## Working across the four repositories

PathFinder is one of four repositories. The other three are libraries it
consumes by URL at a commit:

| Repository | Distribution | Consumed by |
| --- | --- | --- |
| [ai-veupathdb-client](https://github.com/VEuPathDB/ai-veupathdb-client) | `veupathdb-py` (import `veupathdb`) | `apps/api`, and the MCP repository |
| [ai-wdk-mcp](https://github.com/VEuPathDB/ai-wdk-mcp) | `veupathdb-mcp` (import `veupathdb_mcp`) | `apps/api`, and the `wdk-mcp` image |
| [ai-assistant-platform](https://github.com/VEuPathDB/ai-assistant-platform) | `assistant-core`, `veupathdb-mcp-conformance`, `@pathfinder/assistant-client` | `apps/api`, `apps/web` |

The pins are `apps/api/pyproject.toml` `[tool.uv.sources]` (four rows, each a
`tag`), `apps/web/package.json` (`@pathfinder/assistant-client`, a `tag=`) and
the `wdk-mcp` compose service's build context, which names the same release.
A tag is a release of that repository: `v0.1.0a1` for the client and the MCP
server, `v0.2.0a1` for the platform. The lockfile still records the commit the
tag pointed at, so a build is reproducible even though the pin reads as a
version. A tag never moves; a new release gets a new tag.

### Iterating on a library

Clone the repositories you are changing beside this one, then override the pin
inside the api's environment:

```bash
cd apps/api
uv pip install --python .venv/bin/python -e ../../../ai-veupathdb-client
```

`--python` is not optional: without it `uv pip` installs into whatever
interpreter the shell resolves first, which is not this project's environment.

The override lasts until the next `uv sync`, which restores the pin. The runtime
carries its wire document inside the package (`assistant_core/PROTOCOL.md`), so
an editable override of it serves the same document a wheel does.

### Taking a new commit of a library

```bash
cd apps/api
# change `rev` in [tool.uv.sources]
uv lock --upgrade-package veupathdb-py    # or veupathdb-mcp, assistant-core, veupathdb-mcp-conformance
uv sync
```

For the TypeScript client, change the `commit=` in `apps/web/package.json` and
run `yarn install --no-immutable` at the repository root: the root `.yarnrc.yml`
enables immutable installs, so a plain `yarn install` refuses to rewrite the lock
for the new pin. For the `wdk-mcp` image, set
the tag in the `wdk-mcp` compose build context.

A repository that adopts the `v<version>` tag convention can be named by `rev`
or `commit=` with the tag instead of the sha; the pin stays exact either way.

## Architectural enforcement

Three checks enforce structure beyond linting.

**File size cap.** `apps/api/scripts/check_max_lines.py` fails when a Python
source file under `apps/api/src/pathfinder` exceeds 400 meaningful lines,
counting neither blanks nor comments. Devtools and two declared pure-model
modules are exempt; the exemption set is in the script. Tests obey the cap:
`src/pathfinder/tests/.max-lines-baseline.txt` ratchets the files that were
already over it, and a baselined file fails as soon as it grows past its
recorded count. Run `--write-baseline` only to regenerate the whole list.

**Import linter.** `[tool.importlinter]` in `apps/api/pyproject.toml` holds the
five backend layer contracts. `uv run lint-imports` reports which one broke.

**Boundary checker.** `apps/web/scripts/check-boundaries.mjs` refuses an import
from one feature into another. Exemptions live in the script.

## Security scanning

`.github/workflows/security.yml` runs on push and pull request to `main`, and
weekly:

- Trivy for known CVEs in dependencies (CRITICAL and HIGH)
- TruffleHog for verified secrets in history
- CodeQL for Python and JavaScript static analysis

`pip-audit` runs locally as a push-stage hook.
