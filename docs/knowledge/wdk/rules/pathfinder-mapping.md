---
type: Rules
title: PathFinder mapping rules
description: The eight invariants that keep PathFinder's types and layers aligned with WDK - which are machine-checked by an import contract, which are checked by a test, and which are checked by nothing.
tags: [wdk-alignment, rules, layering, types, import-linter]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# WDK-MAP - correspondence, ownership, and what actually checks them

Every rule here is `CONTRACT`: none of them is a fact about WDK, all of them are
invariants PathFinder holds so that its own types keep meaning what WDK's mean.
The `upstream` field names the WDK definition each one is a mapping *of*, so the
rule is falsified when that definition changes.

This is the one family where enforcement is often real, because five of the eight
are checked by `import-linter` contracts declared under `[tool.importlinter]` in
`apps/api/pyproject.toml`. A named contract is enforcement in the strict sense:
`cd apps/api && uv run lint-imports` fails when the rule is broken. Where the
contract covers only part of the rule, the status is `PARTIAL` and the body names
the part it does not cover. The explanation of what each contract can and cannot
see is in [layer-ownership](../pathfinder/layer-ownership.md).

### WDK-MAP-001 - A twelfth `ParamKind` would go unnoticed, while removing one of the eleven would not

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/param/ParamFormatterFactory.java#L18-L55
- anchor: apps/api/src/pathfinder/domain/parameters/value_codec.py:_WIRE_BUILDERS
- status: ENFORCED by apps/api/src/pathfinder/tests/unit/domain/parameters/test_value_codec_wire.py::test_wdk_map_001_a_twelfth_kind_has_no_wire_form

That there are eleven types, and that `ParamKind` is exactly those eleven, is
[WDK-PARAM-001](parameters-and-vocabularies.md#wdk-param-001---there-are-eleven-parameter-types-displaytype-is-a-fifth-and-later-axis-and-never-changes-the-value-shape).
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
`tests/unit/domain/parameters/test_values.py` looks like the test that
would notice and is not: every case is `decode(encode(x)) == x`, which constrains
the codec rather than the enumeration, and `[tool.mypy]` in
`apps/api/pyproject.toml` excludes `src/pathfinder/tests/`, so its literals are
not type-checked either.

The correspondence, cell by cell, is in
[type-correspondence](../pathfinder/type-correspondence.md).

### WDK-MAP-002 - A parameter's declaration is integration-owned and its value is domain-owned; only the value reaches the wire

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L54-L64
- anchor: apps/api/src/pathfinder/integrations/veupathdb/wdk_parameters.py:WDKParameter
- status: PARTIAL by apps/api/pyproject.toml::Domain layer is pure (no I/O, no other layers)

Upstream keeps one type. `ParameterBase` carries `initialDisplayValue` alongside
`dependentParams`, `isVisible` and the rest, so a wdk-client `Parameter` is the
declaration and the current value at once. PathFinder splits them: `WDKParameter`
in `integrations/` is the declaration, `ParamValue` in `domain/` is the value.

The split has to hold in the direction that matters. A parameter *value* crosses
every layer - it is in `StepResponse.parameters`, in agent tool arguments, in the
persisted `StrategyAst` - while a parameter *declaration* is an integration
artifact that reaches the browser only after being normalized into
`ParamSpecResponse`. On 2026-08-10 `openapi.json` held 283 schemas and not one of
them was a `WDKParameter` member.

The named contract enforces one half and does so strictly: it is the only one of
the six without `allow_indirect_imports`, so `domain/parameters/values.py` cannot
reach `integrations/` even through a chain, and the value models therefore cannot
quietly grow a dependency on the spec models.

**Two halves are uncovered, not one.**

*The wire.* Nothing stops a `WDKSearchConfig` or a `WDKParameter` being added to a
response model in `services/` and appearing in `openapi.json` tomorrow; the
contract permits `services -> integrations` by design. The 283-schema measurement
above is a fact about today, not a gate.

*The other side of the split.* The contract stops `domain/` from **importing** a
declaration model. It cannot stop one from being **written** there. A new
`WDKFilterParam`-shaped model defined in `domain/parameters/` would collapse the
split entirely with every contract green, because nothing about it would be an
import at all. What guards the split today is that the declaration models happen to
live in `integrations/`, which is a fact about the file tree rather than a check.

### WDK-MAP-003 - Structure and step data are separate in storage, and the nested tree exists only where it meets WDK

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepFormatter.java#L129-L140
- anchor: apps/api/src/pathfinder/domain/strategy/graph_model.py:flatten_tree
- status: ENFORCED by apps/api/src/pathfinder/tests/unit/services/strategies/test_wdk_pushed_step_tree.py::test_wdk_map_003_the_serialized_tree_carries_only_the_three_keys

`formatAsStepTree` writes a node as `stepId` plus optional `primaryInput` and
`secondaryInput` and nothing else, and the client type says the same
([`StepTree`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkUser.ts#L145-L150)).
The data lives in a sibling `steps` map. PathFinder holds the same separation
internally, with `flatten_tree` producing a step map that carries parent pointers
instead of children, and `rebuild_tree` reconstructing the nested form for the WDK
projection ([nested-tree-at-the-wire-boundary](../../decisions/nested-tree-at-the-wire-boundary.md)).

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
([WDK-STRAT-006](strategies-and-steps.md)), one representation short of the wire.

### WDK-MAP-004 - An AI tool reaches WDK through a service function and never imports `pathfinder.integrations`

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/filter/CheckLoginFilter.java#L135-L148
- anchor: apps/api/src/pathfinder/services/wdk/step_preview.py:step_sample_records
- status: ENFORCED by apps/api/pyproject.toml::Transport and AI never import integrations or persistence directly

The reason is WDK's, not ours. Identity travels on a cookie the *client object*
holds, and a request without one is not refused - a new guest is minted for it
([WDK-AUTH-001](auth-and-transport.md)). A tool that built its own client would
therefore run as **a different user, and a fresh one on every request**. That
guest owns nothing: its strategy list is `[]`, its step ids 404, and each of those
is a 200 or a plausible-looking refusal rather than an error that names the cause.
Nothing about that failure is loud, and the number reaches a researcher through the
model.

Be precise about the mechanism, because the neighbouring claim is not established.
What makes a self-built client dangerous is **identity discontinuity**, measured in
[WDK-AUTH-001](auth-and-transport.md) - three consecutive uncredentialed calls
returned three different user ids. It is *not* that a missing `JSESSIONID` makes a
process query return zero; that belief did not reproduce, and
[WDK-AUTH-003](auth-and-transport.md) declines to assert it for exactly that
reason. A cookie-less `GenesByOrthologPattern` returned `totalCount` a large result on
plasmodb.org on 2026-08-10 ([transport-quirks](../rest/transport-quirks.md)).

So a tool never holds a client. It calls a function in `services/wdk/`, which
holds the client for the length of one call: `step_sample_records` and
`step_download_url` read a built step, and `step_results_service` hands back the
reader for one. `services/wdk/__init__.py` exports nothing at all - it used to
re-export two dozen integration names, which satisfied the contract by aliasing
it ([the service-layer decision](../../decisions/the-wdk-service-layer-holds-functions-not-re-exports.md)).
The contract is enforcement in the strict sense - it fails the build on the
import - and it has been red: one edge ran from `catalog_discovery` into a WDK
client wrapper that belonged in the service layer, and moving the wrapper
cleared it. A gate that has never been red is a gate nobody has tested; this one
has been.

Note what the contract does **not** say. It forbids the import path, not the
type, and it carries four named exceptions: the FRAME tool modules annotate a
search definition with `WDKSearch`, which is a frozen response model. The symbol
those four may name is pinned by
`tests/unit/services/wdk/test_no_integration_facade.py`, because a contract
cannot see a name. Nor does the contract forbid `httpx`, which is on only the
domain contract's list - a tool that built its own client would break the
reasoning above with every contract green. That proposition is not this rule's;
it belongs to
[WDK-MAP-005](#wdk-map-005---only-integrationsveupathdb-may-open-a-connection-to-a-wdk-host-and-no-contract-can-see-that),
and it is `UNENFORCED` there. The status here is `ENFORCED` for the import
prohibition this rule states, and for nothing wider.

### WDK-MAP-005 - Only `integrations/veupathdb` may open a connection to a WDK host, and no contract can see that

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/service/SessionService.java#L277-L311
- anchor: apps/api/src/pathfinder/transport/http/routers/veupathdb_auth.py:logout
- status: ENFORCED by apps/api/src/pathfinder/tests/unit/integrations/veupathdb/test_call_sites.py::test_wdk_map_005_no_module_outside_the_integration_builds_a_site_client

**This rule was briefly marked `PARTIAL by` the layering contract that forbids
transport an integration import, and that was wrong.** That contract enforces a
different proposition. It says a transport module
must not name `pathfinder.integrations` in an import; this rule says nothing
outside `integrations/veupathdb` may open a connection to a WDK host. The two
coincide only by accident. Breaking this rule from `services/`, which is permitted
to import `integrations` freely, leaves every contract green - and so does
breaking it from `transport/` with a raw `httpx` client, which is what actually
happens. A contract with a different scope is not enforcement, however close it
looks, and the rest of this rule is the proof.

What the contract does hold is worth keeping straight: on 2026-08-10, zero modules
under `transport/` import `pathfinder.integrations` or `pathfinder.persistence`.
That is true and it is checked. It is simply not this rule.

**A real check would have to look at call sites, not imports.** The property is
"no `httpx` client is constructed with a VEuPathDB base URL outside
`integrations/veupathdb`", and neither `import-linter` nor any existing test can
express it. The cheapest honest version is a test that walks the AST of every
module outside `integrations/veupathdb`, finds `httpx.AsyncClient(...)` and
`httpx.Client(...)` constructions, and fails on any whose `base_url` argument
derives from `get_site`, `SiteInfo` or a `service_url` attribute. That would catch
today's instance and would not depend on a hostname literal, since the URL is
always resolved from the site router rather than written down.

**`httpx` appears in only one contract's forbidden list, the domain
one**, so a transport module may import it and call a VEuPathDB URL with every
contract green. One did.
`transport/http/routers/veupathdb_auth.py` built
`httpx.AsyncClient(base_url=auth_site.service_url)` and called `GET /logout` on
it, carrying no cookie jar and no `Authorization` header - so by
[WDK-AUTH-001](auth-and-transport.md) the request was served as a fresh guest
and `processLogout` took its early return.

That reading was confirmed live and then fixed: the call moved to
`integrations/veupathdb/auth_login.py:password_logout`, which carries the
credential. What the fix does **not** buy is the property the name suggests -
the bearer token stays valid afterwards
([WDK-AUTH-004](auth-and-transport.md)).

The layering fact is not a reading: it is measured. A transport module opens a
socket to a WDK host, and nothing objects.

### WDK-MAP-006 - A WDK step id is an integer stored beside PathFinder's own string id, never in place of it

- class: CONTRACT
- upstream: https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkUser.ts#L145-L150
- anchor: apps/api/src/pathfinder/services/strategies/schemas.py:wdk_step_id
- status: PARTIAL by apps/api/src/pathfinder/tests/unit/services/strategies/test_materialize_snapshot.py::test_the_snapshot_is_pushed_with_no_wdk_ids_of_its_own

Every WDK id is a number - `StepTree.stepId`, `Step.id`, `Strategy.rootStepId` -
and an `input-step` value is that number stringified
([WDK-PARAM-009](parameters-and-vocabularies.md)). PathFinder's own ids are
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
- anchor: apps/api/src/pathfinder/domain/parameters/wdk_vocab.py:WDKTreeBoxVocabNode
- status: PARTIAL by apps/api/pyproject.toml::Domain layer is pure (no I/O, no other layers)

Some WDK shapes have to reach the browser, because the browser renders them: a
tree vocabulary is `{data: {term, display}, children: [...]}` exactly as
`TreeBoxEnumParamFormatter` writes it, and re-modelling it would only add a lossy
translation between two identical structures.

On 2026-08-10, `openapi.json` held eight `WDK*` schemas - `WDKVocabTerm`,
`WDKVocabNodeData`, `WDKTreeBoxVocabNode`, `WDKFilterOntologyTerm`,
`WDKDatasetParser`, `WDKRecordIdPart`, `WDKHistogramBin`, `WDKHistogramStatistics`
- and **all eight are defined under `domain/`**, five in
`domain/parameters/wdk_vocab.py` and three in `domain/wdk_values.py`. None of the
`WDK*` response models in `integrations/veupathdb/wdk_models.py` appears.

The named contract is what makes "carry no I/O" a fact rather than an intention:
anything in `domain/` is forbidden from importing `httpx`, `sqlalchemy`,
`asyncpg`, `fastapi` or any other layer, through a chain as well as directly. Move
one of these eight into `integrations/` while keeping a domain reference and the
contract fails.

**The uncovered half is which types get added later.** The contract is about where
a type lives, not about what a response model may contain, so it would stay green
if a genuine WDK response model were exposed from `services/`. See
[WDK-MAP-002](#wdk-map-002---a-parameters-declaration-is-integration-owned-and-its-value-is-domain-owned-only-the-value-reaches-the-wire),
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
PathFinder, not for WDK ([deliberate-divergences](../pathfinder/deliberate-divergences.md)).
It is recorded as a rule because the failure mode is a reviewer reading
`Step.id` in frontend code and reasoning about it as a WDK step id, which
[WDK-MAP-006](#wdk-map-006---a-wdk-step-id-is-an-integer-stored-beside-pathfinders-own-string-id-never-in-place-of-it)
says it is not.

Nothing checks this. `check-boundaries.mjs` polices feature isolation rather than
naming, and no test asserts that `@pathfinder/shared` exports no `wdk-client`
type. The full four-column map, including every cell that is empty and why, is in
[type-correspondence](../pathfinder/type-correspondence.md).
