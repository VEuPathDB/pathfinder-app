---
type: Reference
title: Who is allowed to talk to WDK
description: The import-linter contracts that police the WDK boundary, exactly what each one forbids, the seam an upper layer calls instead of holding a WDK client, and the two things the contracts cannot see.
tags: [wdk-alignment, layering, import-linter, ownership, pathfinder]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-08T00:00:00Z }
status: stable
---

Every permalink below is pinned to the sha recorded in sources.md (`veupathdb-py: docs/knowledge/wdk/sources.md`).

# This is checked, so read the check rather than the prose

The layering rule itself is in `CLAUDE.md` and is not repeated here. What is here
is the machine that enforces it, what that machine actually forbids as opposed to
what the prose says, and where it is blind.

Six `forbidden` contracts live under `[tool.importlinter]` in
`apps/api/pyproject.toml`, over
`root_packages = ["pathfinder", "veupathdb", "veupathdb_mcp", "assistant_core"]`
with `include_external_packages = true`. The three libraries are roots and not
external packages because a forbidden contract cannot name a submodule of an
external package. Run them with `cd apps/api && uv run lint-imports`.

| Contract name | Source | Forbidden | Named by a rule? |
|---|---|---|---|
| Transport and AI never import persistence directly | `pathfinder.transport`, `pathfinder.ai` | `persistence` | **no** |
| Services never import transport or AI | `pathfinder.services` | `transport`, `ai`, `pydantic_ai` | **no** |
| Persistence never imports services, transport, or AI | `pathfinder.persistence` | `services`, `transport`, `ai` | **no** |
| The science never imports an assistant's composition root | `ai`, `persistence`, `services` | `assistants` | **no** |
| The agent and the jobs reach the workbench only through its facade | `ai`, `jobs` | the six service modules the facade owns | **no** |
| The application imports no private module of an installed distribution | `pathfinder` | the named `_*` modules of the three libraries | **no** |

**Three contracts left this file rather than being relaxed.** Domain purity and
the integration direction are installation facts of `veupathdb-py`, and the MCP
server's is an installation fact of `veupathdb-mcp`: a package whose lock names
no application cannot import one. See [the client library is a
distribution](../../decisions/the-client-library-is-a-distribution.md) and [the
MCP server is a distribution](../../decisions/the-mcp-server-is-a-distribution.md).

**The last column is this table's own expiry date, and it is not decoration.** This
table restates `pyproject.toml`, so it can go stale the moment a contract is
renamed or dropped. A contract name that appears in a rule's `status` field is
load-bearing: `scripts/check-wdk-rules.mjs` fails when a named selector is no
longer found in the file it points at.

**The rows marked "no" are unguarded.** Nothing connects them to this
document, so if one is renamed or deleted, this table quietly becomes fiction. They
are kept because the asymmetry below is only visible with all of them present, and
because a reader deciding where code belongs needs the whole picture rather than
the checked part of it. Treat them as a snapshot dated 2026-09-08, and read
`pyproject.toml` when it matters.

**Every remaining contract is about import statements, not reachability.** All
six set `allow_indirect_imports = true`, so each fails only on a direct import
statement. Domain purity left with the domain:
`veupathdb-py: tests/unit/test_package_boundary.py` reads every module's import
statements, so a domain module that names `httpx`, or names `veupathdb.wdk` or
`veupathdb.eda` (the two subpackages that open a connection), fails there.

`uv run lint-imports` reports **6 kept, 0 broken**. The contract that forbade
`pathfinder.integrations` to `transport` and `ai` was red twice before the split
- once on a single edge from `catalog_discovery` into a WDK client wrapper that
belonged in the service layer, once on four wire-model edges it carried as
exceptions - and it left this file with the layer it named. See
[WDK-MAP-004](rules/pathfinder-mapping.md).

# The seam: functions in `veupathdb_mcp/wdk/`

Until 2026-09-03 the contract above was satisfied by one module.
`services/wdk/__init__.py` re-exported the WDK client factories and two dozen
WDK types, so an AI tool wrote `from pathfinder.services.wdk import WDKParameter`
and never named `pathfinder.integrations`. That was the contract satisfied by an
alias: the object a caller received was the integration's own, and no check said
which of the twenty-four a caller took.

What an upper layer calls instead is a function that holds a client for the
length of one call - `step_sample_records`, `step_download_url`,
`step_results_service`, `start_veupathdb_session`, `end_veupathdb_session` - and
those functions are now `veupathdb_mcp.wdk`, a distribution of its own. See
[the service-layer decision](../../decisions/the-wdk-service-layer-holds-functions-not-re-exports.md).

**The type edge stopped needing an exemption.** Four FRAME tool modules annotate
a WDK search definition with `WDKSearch`, a frozen response model. It used to be
four `ignore_imports` lines and a test that read the syntax tree, because a
contract cannot see which symbol an edge carries. `WDKSearch` is now a
third-party name from this application's point of view, so there is no contract
to except and no facade to police.

# The two things the contracts cannot see

## A raw HTTP call to a WDK host

A contract reads import statements. It says nothing about importing `httpx` and
calling a VEuPathDB URL, because `httpx` is only in the forbidden list of the
client library's own domain suite.

Most non-test modules under `src/pathfinder/` that import `httpx` catch its
exception types without making a call; the literature clients under
`services/research/` call arXiv, Crossref, PubMed and the rest. Exactly one built
a client against a VEuPathDB base URL:
`transport/http/routers/veupathdb_auth.py` constructed its own
`httpx.AsyncClient(base_url=auth_site.service_url)` for `GET /logout`, with every
contract green, and it was a transport module talking to WDK. That call moved
into `veupathdb/wdk/auth_login.py`, where the credential it needs already lives.

The reading behind that move was confirmed live and is now
WDK-AUTH-004 (`veupathdb-py: docs/knowledge/wdk/rules/auth-and-transport.md`), which also records the part a fix
cannot reach - the bearer token survives the logout either way.

What closes the hole is not a contract but a call-site walk.
[WDK-MAP-005](rules/pathfinder-mapping.md) is `ENFORCED by` a test that parses
every non-test module in this tree and fails on an `httpx` client whose
`base_url` resolves from the site router. A contract could not hold it: it
forbids an import, which is a different proposition.

## Which types cross a boundary

A contract is about modules, not about the types that flow between them. So the
question "where may a WDK type appear" is answered by a different measurement.

Eight of `openapi.json`'s schemas are named `WDK*`: `WDKVocabTerm`,
`WDKVocabNodeData`, `WDKTreeBoxVocabNode`, `WDKFilterOntologyTerm`,
`WDKDatasetParser`, `WDKRecordIdPart`, `WDKHistogramBin`, `WDKHistogramStatistics`.
**All eight are the client's value objects** - five in
`veupathdb-py: src/veupathdb/domain/parameters/wdk_vocab.py`, three in
`veupathdb-py: src/veupathdb/domain/wdk_values.py`. Not one of the `WDK*`
response models in `veupathdb.wdk.wdk_models` reaches the wire.

So the answer is: a WDK-*shaped* type may reach the browser if it is a pure value
object, and a WDK-*response* type may not reach the wire at all. That is
[WDK-MAP-007](rules/pathfinder-mapping.md). Both halves are now installation
facts of `veupathdb-py`: the value objects are `veupathdb.domain`, whose boundary
suite asserts it opens no connection, and the response models are
`veupathdb.wdk.wdk_models`, which the wire generator never reaches because no
`pathfinder.transport` module names one.

# Why an AI tool calls a service and not an integration

The layering answer is in `CLAUDE.md`. The WDK-specific answer is not, and it is
the one that matters here: **a WDK conversation is stateful, and the state lives on
the client object.**

WDK identity travels as an `Authorization` cookie, and a request that arrives
without one is not rejected - a new guest is minted for it, **a different one each
time** (WDK-AUTH-001, `veupathdb-py: docs/knowledge/wdk/rules/auth-and-transport.md`). A client built without that
cookie is therefore a different user on every call, and nothing says so. A client
reused across identities has the mirror-image problem: it can carry the previous
identity's `JSESSIONID` into the next call, which can only ever bind the request to
the wrong container session, so PathFinder drops it whenever the effective token
changes (WDK-AUTH-003, `veupathdb-py: docs/knowledge/wdk/rules/auth-and-transport.md`).

What that costs is continuity of identity, and nothing weaker. An agent tool that
built its own client would not fail loudly: it would act as a guest that owns
nothing, so a strategy it created on one call is invisible on the next, the list
comes back `[]` rather than an error, and the model reports that emptiness to a
researcher as a finding. That is the failure mode the whole `SILENT` class in
the rules (`veupathdb-py: docs/knowledge/wdk/rules/`) exists to name, and it is why a tool calls a
service rather than a URL: the service layer takes `get_strategy_api()` from
`veupathdb.wdk.factory`, and no module under `ai/` names it.

Since 2026-08-19 the silent half of that is closed from two directions: VEuPathDB
refuses a guest identity outright, and `_http.py` refuses a user-scoped call that
carries no request token before it leaves the process
(WDK-AUTH-001, `veupathdb-py: docs/knowledge/wdk/rules/auth-and-transport.md`). The continuity argument for one
client per site is unchanged.

Do **not** reach for the other explanation. The belief that a process query returns
zero without a `JSESSIONID` did not reproduce - a cookie-less
`GenesByOrthologPattern` returned `totalCount` a large result - and it is recorded as an open
question in transport-quirks (`veupathdb-py: docs/knowledge/wdk/rest/transport-quirks.md`) rather than as a rule.
The identity argument above is the one that is measured.

# The frontend does not speak to WDK at all

Measured on 2026-08-10 across `apps/web/src`: three files contain a VEuPathDB URL
and all three are `.test.tsx` fixtures for `wdkUrl`, a string the backend supplies
and the UI renders as an `href`. No non-test file contains a `*db.org` URL or a
`/service/` path, and no component fetches one.

The browser's entire view of WDK is whatever `openapi.json` describes, which is the
eight domain-owned value types above plus PathFinder's own projections. Adding a
direct call from the browser to plasmodb.org would break nothing mechanical today -
`check-boundaries.mjs` polices feature isolation, not hostnames - so this section
is a measurement rather than a guarantee.
