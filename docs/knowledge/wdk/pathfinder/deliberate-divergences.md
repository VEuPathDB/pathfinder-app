---
type: Reference
title: Where PathFinder deliberately differs from WDK
description: Nine places PathFinder does something other than what WDK does, each with the reason and the decision that records what was rejected - and the test that separates these from the bugs in the backlog.
tags: [wdk-alignment, divergence, decisions, pathfinder]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

Every permalink below is pinned to the sha recorded in sources.md (`veupathdb-py: docs/knowledge/wdk/sources.md`).

# A divergence is not a defect, and the difference is testable

`CLAUDE.md` says that when PathFinder disagrees with WDK, PathFinder is wrong.
That is the right default and this page is the list of exceptions to it, which
makes it the most dangerous page in the bundle: anything filed here stops being
investigated.

So there is one admission test. **A divergence belongs here only if the WDK
behaviour was understood, an alternative existed, and the alternative was
rejected for a stated reason.** Where a `decisions/` file records that rejection,
it is linked and not restated. Where none exists, the entry says so in bold, and
that is a flag rather than a footnote.

Everything else is a bug and lives in [backlog](../../backlog/index.md), whose
WDK-integration section holds them. Those are disagreements with WDK where
PathFinder is simply wrong; naming individual ones here only dates this page as
they get fixed. Moving one of them onto this page would end the investigation,
which is exactly the harm the test above exists to prevent.

# 1. The nested tree lives only at the wire boundary

**WDK.** A strategy carries structure and data separately:
[`stepTree`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkUser.ts#L145-L150)
is nested and holds only `stepId`
(WDK-STRAT-001, `veupathdb-py: docs/knowledge/wdk/rules/strategies-and-steps.md`), and `steps` is a flat map.

**PathFinder.** Flatter still: `StrategyGraph` holds a step map with parent
pointers, and the nested form is rebuilt only when projecting to WDK.
`StrategyAst`, which is what gets persisted and what crosses the wire to the
browser, stays nested.

**Why.** Recorded in
[nested-tree-at-the-wire-boundary](../../decisions/nested-tree-at-the-wire-boundary.md).
The rejected alternative was flattening the persisted shape too, which would have
required a data migration for no gain. This is a move toward WDK rather than away
from it: the aliasing bug it fixed came from `StrategyStepNode` nesting whole
nodes, which WDK's own model never does.

The shape itself is not cosmetic - `A INTERSECT (B UNION C)` is a different
question from `(A INTERSECT B) UNION C`, and a left fold lost a real gene
([structure-is-a-tree](../../decisions/structure-is-a-tree.md),
WDK-STRAT-006 in `veupathdb-py: docs/knowledge/wdk/rules/strategies-and-steps.md`).

Rule: [WDK-MAP-003](rules/pathfinder-mapping.md).

# 2. A step has a status, which WDK has no field for

**WDK.** A step document carries `validation` and nothing resembling a lifecycle.
The
[whole field list](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepFormatter.java#L75-L95)
is one chained expression with no status key, and the only field added outside it
is [`estimatedSize`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Service/src/main/java/org/gusdb/wdk/service/formatter/StepFormatter.java#L106-L116),
whose absence means four different things and never means "unbuilt"
(WDK-VALID-005, `veupathdb-py: docs/knowledge/wdk/rules/validation.md`). WDK does not need a status: a step
exists from the moment it is `POST`ed, so "not yet built" is not a state it can be
in.

**PathFinder.** `StepStatus` is four states - draft, ready, built, invalid -
derived on every read from wiring, WDK id and validation.

**Why.** Recorded in
[step-status-is-derived](../../decisions/step-status-is-derived.md). Two
alternatives were rejected: storing the status (a stored copy needs updating at
every push, edit and rewire, and one missed path leaves a step claiming to be
built when it is not), and the three-state version, which classified a complete
but unpushed step as a draft and would have deferred it forever.

This divergence exists because PathFinder models something WDK cannot: a step a
researcher is still composing. Note that the derivation must not run backwards -
a step already live in WDK is never demoted to draft, because that would drop it
from the built strategy.

PathFinder derives its own four-state step status rather than storing one, for the same
reason WDK recomputes a bundle on every read
([step-status-is-derived](../../decisions/step-status-is-derived.md)).

# 3. The local edit is the truth; a WDK rejection is that step's problem

**WDK.** A rejected write is a status code. `PUT .../search-config` answers 4xx
with a validation bundle (WDK-VALID-006, `veupathdb-py: docs/knowledge/wdk/rules/validation.md`), and the
reference client's model is that WDK is the store of record.

**PathFinder.** The edit is applied in memory and persisted first, then pushed.
A push rejection comes back inside a 200 as `CommitResult.failed_step_ids`, is
made durable as `StrategyAst.wdk_push_errors`, and reaches the browser as
`StepResponse.wdkPushError`.

**Why.** Recorded in
[local-edit-is-the-truth](../../decisions/local-edit-is-the-truth.md). The
rejected alternative - raising a 502 - was actively wrong rather than merely
worse: the edit had already been written to Postgres, so the client rolled its
cache back and the server handed the change straight back on the next read.
Memory, Postgres, WDK and the canvas told four different stories.

WDK recomputes a step's validation against the model in force, so a bundle is a reading
of that step now, not a record of what the write did. That is why invalid steps show up
on old saved strategies and almost never on new ones, and it is why PathFinder treats a
WDK rejection as that step's problem rather than as a failure of the operation.

# 4. `COLOCATE` is a PathFinder operator that WDK's boolean search will not take

**WDK.** The boolean operator parameter's vocabulary is built from
[`BooleanOperator.values()`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/BooleanQuery.java#L178-L195),
using each member's base operator as both term and internal value. That is
exactly six terms:
[`UNION`, `INTERSECT`, `MINUS`, `RMINUS`, `LONLY`, `RONLY`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/model/query/BooleanOperator.java#L14-L21).
`BooleanOperator.parse` additionally accepts aliases such as `or`, `and` and
`not`, but those are not vocabulary terms, so a step that sends one fails
membership validation before `parse` is ever reached.

**PathFinder.** `CombineOp` has seven members - WDK's six plus `COLOCATE` - and
`BOOLEAN_OPERATORS` is defined as `frozenset(CombineOp) - {CombineOp.COLOCATE}`,
which is WDK's six exactly. `BooleanOperator` is `CombineOp` narrowed by an
`AfterValidator` to that set.

**Why.** Recorded in
[boolean-operator-is-a-type](../../decisions/boolean-operator-is-a-type.md). WDK
does colocation through a separate search, `GenesBySpanLogic`, not through a
boolean operator, so a single enum cannot be right in both places. The rejected
alternative was restating the constraint at each boundary; making it a type means
an unknown operator is a 422 at the edge and the agent's tool schema cannot offer
it at all.

# 5. A PathFinder step id is a string, and it is not a WDK step id

**WDK.** Every id is a number:
[`StepTree.stepId`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkUser.ts#L145-L150)
and `Step.id` are both `number`, and an `input-step` value is
`Long.toString(step.getStepId())` on the wire
(WDK-PARAM-009, `veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`).

**PathFinder.** `StepResponse.id` is a `str` and `StepResponse.wdkStepId` is a
separate `int | None`. A locally created step gets `step_<8 hex>`; a step imported
from WDK takes `str(step_id)`, so its local id is its WDK id in string form. The
projection reads a numeric-looking local id back as a WDK id when the explicit map
has no entry for it, which is coherent precisely because a generated id always
begins with `step_` and can never be all digits.

**Why.** A PathFinder step exists before WDK has one, so the id spaces cannot be
the same space - which is the same root as divergence 2.
**No decision file records this**, and the reason above is reconstructed from the
code rather than from a recorded choice. The `isdigit()` reinterpretation in
particular deserves a decision or a test of its own.

Rule: [WDK-MAP-006](rules/pathfinder-mapping.md).

# 6. `@pathfinder/shared` has no WDK type in it

**WDK.** `wdk-client` exports `StrategyDetails`, `Step`, `SearchConfig`,
[`Answer`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L361-L376)
and
[`Reporter`](https://github.com/VEuPathDB/web-monorepo/blob/63d1705463d553c0ac19ee577c1b09666597b903/packages/libs/wdk-client/src/Utils/WdkModel.ts#L45-L52),
because it is a client for WDK.

**PathFinder.** None of those has a counterpart in `@pathfinder/shared`. The
browser sees `StepResponse`, `ConversationResponse` and `RecordsResponse` -
PathFinder's own shapes - plus eight WDK-*shaped* value types that are owned by
`domain/` and carry no I/O. The full cell-by-cell account is in
[type-correspondence](type-correspondence.md).

**Why.** The browser is a client for PathFinder, not for WDK, and PathFinder's
concepts do not line up one to one: a conversation is not a strategy, and a step
may not exist in WDK at all. Making the frontend import `wdk-client` types would
force the two id spaces of divergence 5 into one.
**No decision file records this**, though
[one-way-to-generate-types](../../decisions/one-way-to-generate-types.md) records
how the types that do exist are produced.

# 7. A parent term is expanded to leaves before it is sent

**WDK.** Under `countOnlyLeaves` - the default for tree parameters - selecting a
branch term counts as selecting nothing, and the resulting error names neither the
branch nor the count as the problem
(WDK-VOCAB-002, `veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`).

**PathFinder.** Parent terms are expanded to their leaves at the WDK boundary, so
the value sent is not the value the user chose.

**Why.** The literal alternative - send what was selected - produces
`Number of selected values (0) is not allowed` for a correctly scoped step, which
is the same message WDK gives for a term that does not exist and for the synthetic
`@@fake@@` root. Three different mistakes, one message. The frontend had to learn
the same rule after a correct organism scope rendered as an empty required field
([parent-term-is-a-selection](../../decisions/parent-term-is-a-selection.md)).

This is the one divergence on this page that rewrites a user's value, which is why
it is worth restating that it is a divergence at all.

# 8. A multi-pick slot takes a list, and the encoding happens at the boundary

**WDK.** Every parameter value is a string, including the structured ones, and a
multi-pick value is `json.dumps(list_of_terms)`
(WDK-PARAM-002 and WDK-PARAM-004,
`veupathdb-py: docs/knowledge/wdk/rules/parameters-and-vocabularies.md`).

**PathFinder.** The agent-facing tool slot is a list, not a pre-encoded string,
and `MultiPickValue.to_wire` does the encoding.

**Why.** Recorded in
[a-multi-pick-slot-takes-a-list](../../decisions/a-multi-pick-slot-takes-a-list.md)
and
[an-override-list-stays-a-list](../../decisions/an-override-list-stays-a-list.md).
Making the model hand-encode the array was not merely inconvenient: a `str`-typed
slot produced a Pydantic error the model read as a WDK rejection, and it told the
user WDK had refused a payload WDK accepts. Encoding at the tool boundary in the
other direction turned a whole array into one candidate option.

# 9. A strategy may hold components WDK has nowhere to put

**WDK.** Every step a strategy holds is reachable from its root
(WDK-STRAT-003, `veupathdb-py: docs/knowledge/wdk/rules/strategies-and-steps.md`), and a strategy has exactly
one root (WDK-STRAT-002, `veupathdb-py: docs/knowledge/wdk/rules/strategies-and-steps.md`). There is no
representation of a second, unattached component.

**PathFinder.** `StrategyAst.detached_roots` is a list of exactly that: components
not reachable from `root`, persisted locally and never pushed. The push planner
walks `root` only.

**Why.** Adding a search to an existing strategy leaves two roots until the user
combines them, and that intermediate state has to survive a reload. The
alternatives were both worse than a field WDK never sees: refusing the edit until
the user names the operator, or pushing each component as its own WDK strategy and
reconciling later.
**No decision file records this**, and the field's own docstring is the only
account of it, which is thin for a divergence that changes what "the strategy" means
between two layers.
