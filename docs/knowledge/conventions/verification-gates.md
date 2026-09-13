---
type: Convention
title: Verification gates
description: The exact commands that decide whether a change is done in this repository, for the API, the frontend and the shared packages.
tags: [testing, ci, workflow]
generated: { by: claude-code/opus-5, at: 2026-08-09T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-09T00:00:00Z }
status: stable
---

Gates passing is necessary, not sufficient: see the definition of done in `CLAUDE.md`. These are the commands.

# Backend (`apps/api`)

```
uv run ruff check src/
uv run ruff format --check src/
uv run mypy --strict src/pathfinder/
uv run pyright src/pathfinder/
uv run lint-imports
uv run vulture
uv run pytest --override-ini "addopts=" --collect-only -q
uv run pytest src/pathfinder/tests/ -q
uv run python scripts/check_max_lines.py
uv run python scripts/check_weak_assertions.py
```

Both type checkers read the tests tree. `[tool.mypy]` and the repo-root
`pyrightconfig.json` name no exclusion for `src/pathfinder/tests`, so a test
runs under the same rules as the code it tests and a gate is green only at
zero over both.

The two ratchets cover production and tests alike. `check_max_lines.py` fails a
Python file over 400 meaningful lines; `src/pathfinder/tests/.max-lines-baseline.txt`
records the count each older offender had when the cap reached tests, and a
baselined file fails as soon as it grows past that count. `check_weak_assertions.py`
fails a test whose only assertions pin nothing, suppressed by
`src/pathfinder/tests/.weak-baseline.txt`. An entry leaves either file when the
file shrinks or the test gains a value assertion; an entry never enters one.

The collect runs with `addopts` cleared, so it reaches the tiers the default
run deselects. An opt-in tier is invisible to every other command here, and a
tier nobody imports rots into an import error that looks like coverage. The
collect is the only line that reports it.

`vulture` reads `[tool.vulture]` in `apps/api/pyproject.toml` at
`min_confidence` 80, so it reports unreachable code, unused imports and unused
variables and never an unused function. It must run through `uv run` in the
project environment: an older interpreter on `PATH` reports every PEP 758, PEP
695 and `match` file as a syntax error and silently inspects the rest. See
[the pinning decision](../decisions/the-dead-code-checker-is-a-pinned-dependency.md).

`pyright` is not redundant with `mypy`: it catches variance and invariance errors mypy misses. `ruff format --check` is not redundant with `ruff check` either: the two rule sets do not overlap, and formatting drift is invisible to the linter.

`lint-imports` enforces six layering contracts, declared in `apps/api/pyproject.toml` under `[tool.importlinter]`:

1. Transport and AI never import persistence directly.
2. Services never import transport or AI.
3. Persistence never imports services, transport or AI.
4. The science never imports an assistant's composition root.
5. The agent and the jobs reach the workbench only through its facade.
6. The application imports no private module of an installed distribution.

The sixth names each library's `_*` modules one by one, because a forbidden
contract matches whole module segments and cannot name a submodule of an
external package. The three libraries are therefore `root_packages` beside
`pathfinder`, so the gate needs them installed, which `uv sync` gives it.

Domain purity, the integration direction and the MCP server's isolation are no
longer contracts. They are installation facts of `veupathdb-py` and
`veupathdb-mcp`, whose `tests/unit/test_package_boundary.py` suites assert them
per module; see [the client library is a
distribution](../decisions/the-client-library-is-a-distribution.md). The four
`ignore_imports` that let four FRAME tool modules annotate a WDK search
definition with a wire model went with them: a third-party module needs no
exemption. The embedding index left with the MCP server, and
`pathfinder.integrations` with it, so the contract that forbade it and the test
that named the offending module are both deleted; what holds the property now is
`veupathdb-mcp`'s own `tests/unit/test_package_boundary.py`. See [the MCP server
is a distribution](../decisions/the-mcp-server-is-a-distribution.md).

The unit tier refuses every connection made through Python's socket module. An autouse fixture in `src/pathfinder/tests/unit/conftest.py` patches `socket.socket.connect`, `connect_ex`, `socket.getaddrinfo` and the event loop's `create_connection`/`getaddrinfo`, so a stub that no longer covers its seam fails there instead of passing against a live server. The refusal derives from `BaseException`, because every HTTP client here retries under `except Exception` and would otherwise swallow it.

Two limits are worth knowing. The guard runs per test, so anything at collection time is outside it. And a C extension that opens its own socket without going through the `socket` module is not covered.

A unit test that needs a real connection carries `@pytest.mark.allow_network`. No production test does: the two database-backed ones live in `tests/integration/`, where they belong. A new marked test needs a reason, because the marker is how the guard is defeated.

## The science verifies in two lanes

The WDK rules answer to two suites, and which lane a rule lands in follows from what can falsify it.

**Per-PR, hermetic, hard gate.** Every rule that a pinned response can settle is a test reading a recorded fixture through `veupathdb.testing.wdk_fixtures`, in `veupathdb-py: tests/unit/` when the client alone can settle it and in `apps/api/src/pathfinder/tests/unit/` when it needs a service. It runs in the ordinary unit tier, needs no network and no credential, and blocks a merge. A rule's `status` line names one of these tests, and `node scripts/check-wdk-rules.mjs` resolves the name and reports how many rules are still unenforced.

The same tier holds the schema half. `wdk_fixtures verify` validates each body PathFinder sends or has recorded against the WDK JSON Schema its endpoint annotates, reading the copy vendored under `veupathdb-py: src/veupathdb/testing/fixtures/wdk/schema/`; it is offline, it fails when a vendored file no longer matches the sha256 in `schema-pin.json`, and `veupathdb-py: tests/unit/devtools/` runs it as a test as well as the CLI running it as a gate. Which schemas WDK enforces, and which of its own annotations the service breaks, is WDK-HTTP-004 (`veupathdb-py: docs/knowledge/wdk/rules/auth-and-transport.md`).

**Nightly, live, never blocking.** `pytest -m live_wdk` is the second lane: the same rules against running sites, plus the checks a fixture cannot answer - a search still exists, a vocabulary still carries a pinned term, a sentinel count is still in band, and the pinned fixtures still describe the wire. It skips without `WDK_TEST_EMAIL`/`WDK_TEST_PASSWORD` (or `WDK_TEST_TOKEN`), runs on a schedule in `.github/workflows/wdk-nightly.yml`, and files an issue rather than failing a build. The `apps/api` half of the lane loads site catalogs. A catalog load starts the semantic index sync beside itself and never waits on it, so the lane needs no database: an unreachable one leaves ranking lexical and is logged once. Every resource a live check creates is deleted in teardown: the account is a researcher's own.

```
yarn wdk:live       # run the nightly lane by hand
yarn wdk:record     # re-record the pinned fixtures from live WDK
yarn check:wdk-rules
cd apps/api && uv run python -m veupathdb.devtools.fixtures verify   # offline
cd apps/api && uv run python -m veupathdb.devtools.fixtures vendor   # re-pin
cd apps/api && uv run python -m veupathdb.devtools.eda_schemas verify    # offline
cd apps/api && uv run python -m veupathdb.devtools.eda_schemas vendor    # re-pin
```

**A confirmed drift is answered by re-recording, not by editing a fixture.** No fixture is written by hand. `veupathdb-py: src/veupathdb/devtools/fixtures.py` holds the manifest - what to ask, where, which rules read it, and which schema each direction binds - and `record` refreshes the store. Each file carries its own provenance as data: site, method, url, status, content type, and the date it was recorded. Recording needs `VEUPATHDB_AUTH_TOKEN`, because VEuPathDB refuses anonymous service calls; every manifest entry is user-independent, so no account is addressed.

**A vendored schema is re-downloaded, not edited either.** `vendor` fetches the enforced schemas and their transitive `$ref` closure at the commit the pin names, deletes what the closure no longer reaches, and rewrites the pin only when a byte changed. Moving to a newer WDK is one edit to the pin's `sha` followed by `vendor`; a hand-edited copy fails `verify` instead of passing quietly.

**The EDA fixtures answer the same way.** The recorded EDA bodies under `veupathdb-py: src/veupathdb/testing/fixtures/eda/` are trimmed by hand, so `record` refreshes their provenance rather than their content. `apps/api/src/pathfinder/tests/_support/eda_fixtures.py` holds the manifest - what to ask, where, and what the stored copy drops - and writes `provenance.json` beside the bodies: site, deployment, method, url, status, content type, body shape and the date. `tests/live/test_eda_fixture_drift.py` runs in the `live_wdk` lane and fails when the deployment's body shape no longer matches what a fixture pins, or when a fixture on disk is not in the manifest. Recording needs the same registered account the lane skips without. The schema half is `veupathdb.devtools.eda_schemas verify`: it reads the `service-eda` RAML type library vendored under `veupathdb-py: src/veupathdb/testing/fixtures/eda/upstream/`, converts it to JSON Schema, and validates every recorded EDA body against the type its resource declares; it is offline, fails on a sha256 drift from its own `schema-pin.json`, and absorbs only the divergences `veupathdb-py: docs/knowledge/eda/rest-surface.md` records as defects in the spec.

The lane writes `wdk-live-summary.json`: the run's outcomes, a per-site tally, and the drift list. It is the science layer's feed into the observability contract.

**An unenforced rule must say why.** `check-wdk-rules.mjs` fails a rule whose status is `UNENFORCED` and whose block carries no `reason`. A rule with no test and no reason is a claim nobody is checking.

## The logic verifies as a trend, and is promoted to a gate only by evidence

The assistant's evals answer "did this change make it worse at real tasks", and a bad answer is a judgement, not a crash. So the eval lane is not a gate on arrival.

**An eval starts as a tracked trend.** It runs on demand, it writes its result, and a regression in it is read, not enforced. Nothing blocks on it.

**An eval becomes a hard gate only after it catches, or would have caught, a real regression, and then holds stable.** "Would have caught" counts: a case written from a failure already in the backlog qualifies once it is shown to fail on the code that had the bug and pass on the code that fixed it. "Holds stable" means it has not flipped without the assistant changing.

**A flaking gate is demoted or deleted, never suppressed.** No skip mark, no retry loop, no tolerance widened until the red goes away. A gate that cannot decide is answering a question it cannot answer, and it goes back to being a trend, or it goes.

```
cd apps/api
uv run python -m pathfinder.devtools.evals corpus                 # the cases
uv run python -m pathfinder.devtools.evals run --out summary.json  # run them
```

The corpus lives in `apps/api/src/pathfinder/evals/corpus/`, one JSON file per case, each carrying its own provenance as data. A case arrives one of two ways: promoted from the staging queue by `pathfinder.devtools.evals promote`, or written from a cataloged failure in `backlog/`. No case names a user; see [the linkage decision](../decisions/a-staged-eval-case-carries-its-user-until-promotion.md).

**A case is a thread, not a prompt.** `turns` is a list driven in order on one
conversation id, so a case can pin a state a first message cannot reach: an
edit is a second message over a strategy that already exists. `expected` may
name `stepIdsUnchanged`, read from the persisted strategy's WDK step ids on
both sides of the last turn, and `parameters`, which names per search the
values that search must carry. Every case result also carries the four
distances of [the harness decision](../decisions/the-eval-harness-is-pydantic-evals.md),
on a pass as well as on a failure.

**A building case needs a VEuPathDB login.** Only the model is mocked, so a
case whose expectation names a structure pushes real steps to the site named in
`siteId`. Without `WDK_DEV_EMAIL`/`WDK_DEV_PASSWORD` the run is
unauthenticated, the catalog reads answer 403 and the case reports
`builtStrategy: expected 'true', got 'false'`. The non-building cases need no
credential.

**A run under the deterministic provider tests the pipeline, not the model.** The mock is a script, so a green run says the routing, the materialisation, the persistence and the reported verdict still behave; it does not say a real model would have chosen that route. The corpus is provider-agnostic, so a real-model run is the same command with a different provider.

The run writes `EvalRunSummary`: harness, provider, assistant, per-case verdict and named differences. It is the logic layer's feed into the observability contract.

# The three platform packages

`assistant-core`, `assistant-client-ts` and `mcp-conformance` each run their own
gate set, from their own package root, in their own environment. The commands and
what each one proves are
`assistant-platform: docs/knowledge/conventions/verification-gates.md`.

**Our own MCP server is read by the conformance suite in the live lane.**
`apps/api/src/pathfinder/tests/integration/mcp/` is marked `live_wdk`, so it
skips without `WDK_TEST_EMAIL`/`WDK_TEST_PASSWORD` and without
`WDK_MCP_SERVICE_TOKENS` naming the value the served container carries.
`test_conformance_ours.py` runs the suite as its own process against
`PATHFINDER_MCP_URL` (default `http://localhost:8100/mcp`) with the WDK-backed
account hook, and reads the admission record; `MCP_ADMISSION_REPORT` names where
that record is written for a lane to collect. `.github/workflows/mcp-nightly.yml`
serves the endpoint, runs the lane on a schedule, uploads the record and files
an issue on failure. Like the WDK lane, it never blocks a pull request: an
admitted source is quarantined by an issue, not by a red build.

Only warm sites appear in that run's arguments. A catalog read of a site the
container has not loaded builds a per-site index inside a 2g ceiling and the
kernel kills the process, which is a memory decision and not a conformance
result.

# Frontend (`apps/web`)

```
npx tsc --noEmit
npx eslint src/
node scripts/check-boundaries.mjs
node scripts/check-weak-assertions.mjs
node --test scripts/check-weak-assertions.test.mjs
node scripts/check-no-first-nth.mjs
npx vitest run
```

Both checks are green on the trunk, so a red line names the test the change
just added. `check-weak-assertions.mjs` fails a test whose only matchers pin
nothing (`toBeTruthy`, `toBeNull`, `toBeUndefined`); it carries no baseline,
because every web test now states a value. `check-no-first-nth.mjs` fails an
index-based Playwright locator: `.first()` and `.nth()` hide a strict-mode
collision instead of fixing it, so a spec names what it means to click.

**A throwing query is a value assertion, and the checker knows it.** `getBy*`
and `getAllBy*` throw when nothing matches, so `expect(screen.getByText("3.48"))`
already pins `3.48` whatever matcher follows. The rule needs a string or regex
literal as the query's first argument: a variable pins whatever the test
computed, not a value the file states. `queryBy*` returns null and `findBy*`
returns a promise, so both stay weak. That rule is what
`check-weak-assertions.test.mjs` holds, which is why the checker has a checker.

All three run in CI beside `check:boundaries`.

# Mutation testing (`apps/web`)

```
rm -f .stryker-tmp/incremental.json
./node_modules/.bin/stryker run
```

**Delete `incremental.json` first, every time.** The config sets `incremental: true`, and the cache goes stale: it reports mutants that current tests kill as survived. That cost real time once. If a survivor looks impossible, apply the mutation by hand and run the tests before believing the report.

Last full run: 100.00% across the eight `src/state/strategy` modules, zero survivors, zero uncovered.

# Docker

```
docker compose --env-file .env.dev up -d --build --force-recreate api worker wdk-mcp research-mcp web
```

`--force-recreate` is not optional. Without it, `up -d --build` can build a new image and leave the old container running, so you verify code that is not deployed. Confirm by grepping for a new symbol inside the container before trusting a manual test.
