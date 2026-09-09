---
type: Rules
title: PathFinder mapping rules
description: The eight invariants that keep PathFinder's types and layers aligned with WDK - which test holds each one, which live in this repository's suite and which in the client library's, and which half of a rule nothing holds.
tags: [wdk-alignment, rules, layering, types, import-linter]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-08T00:00:00Z }
status: stable
---

# WDK-MAP - correspondence, ownership, and what actually checks them

Every rule here is `CONTRACT`: none of them is a fact about WDK, all of them are
invariants PathFinder holds so that its own types keep meaning what WDK's mean.
The `upstream` field names the WDK definition each one is a mapping *of*, so the
rule is falsified when that definition changes.

This is the one family where enforcement is often real: all eight name a test
that fails when the rule is broken, five in this repository's suite and three in
the client library's own. Seven are `ENFORCED`; one is `PARTIAL`, where the test
covers only part of the rule and the body names the part it does not cover. No
rule is held by an import contract. The six `forbidden` contracts under
`[tool.importlinter]` in `apps/api/pyproject.toml` are about the layers of
`pathfinder` and about the private modules of the installed distributions, not
about these invariants; what they can and cannot see is in
[layer-ownership](../layer-ownership.md).

### WDK-MAP-001 - A twelfth `ParamKind` would go unnoticed, while removing one of the eleven would not

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/ParamFormatterFactory.java#L18-L55
- anchor: veupathdb-py: src/veupathdb/domain/parameters/value_codec.py:_WIRE_BUILDERS
- status: ENFORCED by veupathdb-py: tests/unit/domain/parameters/test_value_codec_wire.py::test_wdk_map_001_a_twelfth_kind_has_no_wire_form

That there are eleven types, and that `ParamKind` is exactly those eleven, is
WDK-PARAM-001 (`veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`).
Not restated here. This rule asserts only what that one does not: **which
direction of drift PathFinder would notice.**

The cost of getting it wrong is on WDK's side. `ParamFormatterFactory.getFormatter`
is a chain of `instanceof` checks ending in `throw new IllegalArgumentException`,
so a `type` PathFinder invented locally corresponds to no WDK class and to no
formatter - there is no lenient path.

**Removing a member is caught, by mypy over `values.py` itself.**
`_WIRE_BUILDERS`, `_SCALAR_KINDS` and `_SCALAR_VALUE_BY_KIND` are keyed by
`ParamKind` and between them name all eleven literals, so dropping one makes a key
stop matching its own type.

**Adding a twelfth is caught by nothing at all.** `_wire_payload` falls through to
`{"type": kind, "value": wire}` for any kind without a builder, and the union
rejects it at runtime with no test watching.
`veupathdb-py: tests/unit/domain/parameters/test_values.py` looks like the test that
would notice and is not: every case is `decode(encode(x)) == x`, which constrains
the codec rather than the enumeration, and `[tool.mypy]` in
`apps/api/pyproject.toml` excludes `src/pathfinder/tests/`, so its literals are
not type-checked either.

The correspondence, cell by cell, is in
[type-correspondence](../type-correspondence.md).

### WDK-MAP-002 - A parameter's declaration and its value are separate types, and only the value reaches the wire

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L54-L64
- anchor: veupathdb-py: src/veupathdb/wdk/wdk_parameters.py:WDKParameter
- status: ENFORCED by veupathdb-py: tests/unit/test_package_boundary.py::test_the_domain_opens_no_connection

Upstream keeps one type. `ParameterBase` carries `initialDisplayValue` alongside
`dependentParams`, `isVisible` and the rest, so a wdk-client `Parameter` is the
declaration and the current value at once. PathFinder splits them, and both
halves are the client library's: the declaration is `WDKParameter` in
`veupathdb-py: src/veupathdb/wdk/wdk_parameters.py`, the value is `ParamValue` in
`veupathdb-py: src/veupathdb/domain/parameters/values.py`.

The split has to hold in the direction that matters. A parameter *value* crosses
every layer - it is in `StepResponse.parameters`, in agent tool arguments, in the
persisted `StrategyAst` - while a parameter *declaration* is a transport concern:
`apps/api/src/pathfinder/transport/http/routers/sites/params.py` serves it to the
browser only after `veupathdb_mcp.catalog` has normalized it into
`ParamSpecResponse`. On 2026-09-08 `openapi.json` held 308 schemas and not one of
them was a `WDKParameter` member.

The named test enforces one half, and it runs in the client's own suite: it reads
the import statements of every `veupathdb.domain` module and fails on `httpx`,
and its sibling `test_the_domain_names_no_client_module_that_opens_a_connection`
fails on a name in `veupathdb.wdk`, which is where the declaration models live.
The value models therefore cannot quietly grow a dependency on them.

**Two halves are uncovered, not one.**

*The wire.* Nothing stops a `WDKSearchConfig` or a `WDKParameter` being added to a
response model in `services/` and appearing in `openapi.json` tomorrow. The six
`forbidden` contracts in `apps/api/pyproject.toml` name the layers of
`pathfinder` and the private modules of the installed distributions; not one of
them is about which type a response model carries, and the table of what each
forbids is in [layer-ownership](../layer-ownership.md). The 308-schema
measurement above is a fact about today, not a gate.

*The other side of the split.* The boundary suite stops `veupathdb.domain` from
**importing** a declaration model. It cannot stop one from being **written**
there. A new `WDKFilterParam`-shaped model defined in
`veupathdb/domain/parameters/` would collapse the split entirely with every check
green, because nothing about it would be an import at all.

### WDK-MAP-003 - Structure and step data are separate in storage, and the nested tree exists only where it meets WDK

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepFormatter.java#L129-L140
- anchor: veupathdb-py: src/veupathdb/domain/strategy/graph_model.py:flatten_tree
- status: ENFORCED by apps/api/src/pathfinder/tests/unit/services/strategies/test_wdk_pushed_step_tree.py::test_wdk_map_003_the_serialized_tree_carries_only_the_three_keys

`formatAsStepTree` writes a node as `stepId` plus optional `primaryInput` and
`secondaryInput` and nothing else, and the client type says the same
([`StepTree`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkUser.ts#L145-L150)).
The data lives in a sibling `steps` map. PathFinder holds the same separation
internally, with `flatten_tree` producing a step map that carries parent pointers
instead of children, and `rebuild_tree` reconstructing the nested form for the WDK
projection ([nested-tree-at-the-wire-boundary](../../../decisions/nested-tree-at-the-wire-boundary.md)).

Conflating them is not a style question. When the tree held the same step objects
the map held, an in-place edit changed both views, and a half-applied batch
corrupted the graph.

The named test is enforcement of the storage half and is not a round trip: it
asserts over 100 generated trees that no step in the flat map has a
`primary_input` or `secondary_input` attribute at all. Break the separation and it
fails immediately.

**The uncovered half is the boundary.** `test_a_tree_survives_the_split_and_rejoin`
in the same file is pure invertibility - it would pass under any lossless encoding,
including one that never produced WDK's shape - and no test asserts that what
reaches WDK is `{stepId, primaryInput, secondaryInput}`. The closest is
`test_operational_spec.py::TestNestedBranchesReachWdk`, which pins that a `UNION`
branch survives onto the *secondary input* of a `StrategyStepNode`
(WDK-STRAT-006, `veupathdb-py: docs/knowledge/wdk/rules/strategies-and-steps.md`), one representation short of the wire.

### WDK-MAP-004 - An AI tool reaches WDK through a served function and never holds a client

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/filter/CheckLoginFilter.java#L135-L148
- anchor: veupathdb-mcp: src/veupathdb_mcp/wdk/step_preview.py:step_sample_records
- status: ENFORCED by apps/api/src/pathfinder/tests/unit/test_call_sites.py::test_wdk_map_005_no_pathfinder_module_builds_a_site_client

The reason is WDK's, not ours. Identity travels on a cookie the *client object*
holds, and a request without one is not refused - a new guest is minted for it
(WDK-AUTH-001, `veupathdb-py: docs/knowledge/wdk/rules/auth-and-transport.md`). A tool that built its own client would
therefore run as **a different user, and a fresh one on every request**. That
guest owns nothing: its strategy list is `[]`, its step ids 404, and each of those
is a 200 or a plausible-looking refusal rather than an error that names the cause.
Nothing about that failure is loud, and the number reaches a researcher through the
model.

Be precise about the mechanism, because the neighbouring claim is not established.
What makes a self-built client dangerous is **identity discontinuity**, measured in
WDK-AUTH-001 (`veupathdb-py: docs/knowledge/wdk/rules/auth-and-transport.md`) - three consecutive uncredentialed calls
returned three different user ids. It is *not* that a missing `JSESSIONID` makes a
process query return zero; that belief did not reproduce, and
WDK-AUTH-003 (`veupathdb-py: docs/knowledge/wdk/rules/auth-and-transport.md`) declines to assert it for exactly that
reason. A cookie-less `GenesByOrthologPattern` returned `totalCount` a large result on
plasmodb.org on 2026-08-10 (transport-quirks, `veupathdb-py: docs/knowledge/wdk/rest/transport-quirks.md`).

So a tool never holds a client. It calls a function in `veupathdb_mcp.wdk`,
which holds the client for the length of one call: `step_sample_records` and
`step_download_url` read a built step, and `step_results_service` hands back the
reader for one. That package is a separate distribution, and its functions are
the only WDK-shaped surface an agent tool names
([the service-layer decision](../../../decisions/the-wdk-service-layer-holds-functions-not-re-exports.md)).

**The layering contract that used to enforce this is gone with the layer it
named.** Until the split, `import-linter` forbade `pathfinder.integrations` to
`transport` and `ai`, and that contract had been red once: an edge ran from
`catalog_discovery` into a WDK client wrapper that belonged in the service
layer, and moving the wrapper cleared it. There is no `pathfinder.integrations`
any more, so the prohibition is vacuous and the contract term was deleted. What
still checks the proposition is the call-site walk: no module in this tree
constructs an `httpx` client against a site base URL, which is the failure the
prohibition existed to prevent. That test is
[WDK-MAP-005](#wdk-map-005---no-pathfinder-module-opens-a-connection-to-a-wdk-host-and-no-contract-can-see-that)'s,
and it holds for this rule too because a tool that holds no client cannot be a
different user.

### WDK-MAP-005 - No `pathfinder` module opens a connection to a WDK host, and no contract can see that

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/SessionService.java#L277-L311
- anchor: apps/api/src/pathfinder/transport/http/routers/veupathdb_auth.py:logout
- status: ENFORCED by apps/api/src/pathfinder/tests/unit/test_call_sites.py::test_wdk_map_005_no_pathfinder_module_builds_a_site_client

The WDK transport is the client library's (`veupathdb-py`, `veupathdb/wdk/`).
This application holds none of it: a `pathfinder` module that builds its own
client to a site is a second WDK caller with its own credential handling, and
the site answers it as a different user than the one the request is for.

**No import contract can express that.** A contract reads import statements,
and the property is about a call: `httpx.AsyncClient(base_url=...)` where the
base url resolves from the site router. `httpx` is forbidden only to `domain/`,
so any other layer may import it and reach a WDK host with all six contracts
green. The scope of an import contract and the scope of this rule coincide only
by accident.

**The check therefore walks call sites.** The named test parses every
non-test module in this tree, finds `httpx.AsyncClient(...)` and
`httpx.Client(...)` constructions, and fails on any whose `base_url` argument
derives from `get_site`, `SiteInfo` or a `service_url` attribute. It depends on
no hostname literal, because the url is always resolved from the site router
rather than written down.

The rule is anchored on the call that broke it.
`transport/http/routers/veupathdb_auth.py` built
`httpx.AsyncClient(base_url=auth_site.service_url)` and called `GET /logout` on
it, carrying no cookie jar and no `Authorization` header - so by
WDK-AUTH-001 (`veupathdb-py: docs/knowledge/wdk/rules/auth-and-transport.md`) the
request was served as a fresh guest and `processLogout` took its early return.
The call now goes through `veupathdb/wdk/auth_login.py:password_logout`, which
carries the credential. What that does **not** buy is the property the name
suggests: the bearer token stays valid afterwards
(WDK-AUTH-004, `veupathdb-py: docs/knowledge/wdk/rules/auth-and-transport.md`).

### WDK-MAP-006 - A WDK step id is an integer stored beside PathFinder's own string id, never in place of it

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkUser.ts#L145-L150
- anchor: apps/api/src/pathfinder/services/strategies/schemas.py:wdk_step_id
- status: PARTIAL by apps/api/src/pathfinder/tests/unit/services/strategies/test_materialize_snapshot.py::test_the_snapshot_is_pushed_with_no_wdk_ids_of_its_own

Every WDK id is a number - `StepTree.stepId`, `Step.id`, `Strategy.rootStepId` -
and an `input-step` value is that number stringified
(WDK-PARAM-009, `veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`). PathFinder's own ids are
strings, because a step exists in a conversation before WDK has one. `StepResponse`
therefore carries `id: str` and `wdk_step_id: int | None` as separate fields, and
`StrategyAst.wdk_step_ids` is the map between them.

The two spaces must not merge, and forking is where they nearly did. The named
test materializes a three-step snapshot whose source WDK ids are 15/13/14, pushes
it as a strategy of its own, asserts the three local keys are unchanged and now
point at the pushed ids 7000/7001/7002, and then asserts the old and new id sets
are **disjoint**. It fails if a fork ever lets a parent's WDK id survive into a
child, which is exactly the aliasing this rule exists to prevent.

**The uncovered half is the reverse reading.**
`step_response_from_strategy_ast` treats a local id as a WDK id when the map has
no entry and `step.id.isdigit()`. That is coherent - a generated id is
`step_<8 hex>` and can never be all digits, while a step imported from WDK takes
`str(step_id)` as its local id - but nothing asserts either premise, so nothing
would notice if the id generator ever emitted digits.

### WDK-MAP-007 - The WDK-shaped types that reach the browser are owned by `domain/` and carry no I/O

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/TreeBoxEnumParamFormatter.java#L30-L51
- anchor: veupathdb-py: src/veupathdb/domain/parameters/wdk_vocab.py:WDKTreeBoxVocabNode
- status: ENFORCED by veupathdb-py: tests/unit/test_package_boundary.py::test_the_domain_opens_no_connection

Some WDK shapes have to reach the browser, because the browser renders them: a
tree vocabulary is `{data: {term, display}, children: [...]}` exactly as
`TreeBoxEnumParamFormatter` writes it, and re-modelling it would only add a lossy
translation between two identical structures.

`openapi.json` holds eight `WDK*` schemas - `WDKVocabTerm`, `WDKVocabNodeData`,
`WDKTreeBoxVocabNode`, `WDKFilterOntologyTerm`, `WDKDatasetParser`,
`WDKRecordIdPart`, `WDKHistogramBin`, `WDKHistogramStatistics` - and **all eight
are the client's domain models**, five in
`veupathdb-py: src/veupathdb/domain/parameters/wdk_vocab.py` and three in
`veupathdb-py: src/veupathdb/domain/wdk_values.py`. None of the `WDK*` response
models in `veupathdb-py: src/veupathdb/wdk/wdk_models.py` appears.

The named test is what makes "carry no I/O" a fact rather than an intention: it
walks every module of the client's domain package and fails if any of them
reaches `httpx`, through a chain as well as directly. Give one of these eight a
transport import and it fails.

**The uncovered half is which types get added later.** The contract is about where
a type lives, not about what a response model may contain, so it would stay green
if a genuine WDK response model were exposed from `services/`. See
[WDK-MAP-002](#wdk-map-002---a-parameters-declaration-and-its-value-are-separate-types-and-only-the-value-reaches-the-wire),
which has the same gap for the same reason.

### WDK-MAP-008 - `Strategy`, `Step`, `Search` and `RecordType` in `@pathfinder/shared` are PathFinder types wearing WDK names

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkUser.ts#L59-L79
- anchor: packages/shared-ts/src/types.ts:StrategyAst
- status: ENFORCED by apps/api/src/pathfinder/tests/unit/test_shared_names_are_pathfinder_types.py::test_wdk_map_008_no_name_carries_the_wdk_shape

Four names collide with `wdk-client` and none of them means the same thing.

| `@pathfinder/shared` | is | `wdk-client`'s type of that name is |
|---|---|---|
| `Strategy` | a `ConversationResponse` with its steps inlined | a `StrategyDetails`: `stepTree` plus a `steps` map |
| `Step` | a `StepResponse`, which may exist only in PathFinder | a WDK step, which exists because WDK created it |
| `Search` | four fields from a listing endpoint | a `Question`: `paramNames`, `groups`, allowed input record classes, default attributes |
| `RecordType` | three fields from a listing endpoint | a `RecordClass`: attributes, tables, formats, searches |

The collision is not accidental and not wrong - the browser is a client for
PathFinder, not for WDK ([deliberate-divergences](../deliberate-divergences.md)).
It is recorded as a rule because the failure mode is a reviewer reading
`Step.id` in frontend code and reasoning about it as a WDK step id, which
[WDK-MAP-006](#wdk-map-006---a-wdk-step-id-is-an-integer-stored-beside-pathfinders-own-string-id-never-in-place-of-it)
says it is not.

Nothing checks this. `check-boundaries.mjs` polices feature isolation rather than
naming, and no test asserts that `@pathfinder/shared` exports no `wdk-client`
type. The full four-column map, including every cell that is empty and why, is in
[type-correspondence](../type-correspondence.md).
