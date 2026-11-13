---
type: Decision
title: An EDA export begins the strategy when the thread has none
description: Exporting the thread's open EDA analysis as a step on a thread with no strategy now creates that strategy with the EDA step as its root, pushed on the same commit, through the one commit path the agent's own first step uses; disabling the export button until a strategy exists was rejected. The blanket "Strategy AST missing" 404 in strategy_ops.apply_operation is gone, an operation that genuinely needs a graph is refused by the op algebra with a 422, and a stored AST that does not parse raises StrategyAstCorruptError rather than reading as an empty strategy.
tags: [eda, strategy, export, transport, wdk]
generated: { by: claude-code/opus-5, at: 2026-08-28T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-28T00:00:00Z }
status: stable
---

# What was decided

The EDA tab's "Export as step" and the `create_eda_step` tool both commit
through `ConversationService.apply_operation`. That function refused every
operation on a thread whose `conversation_strategies` row is absent or holds an
empty AST, with 404 `STRATEGY_NOT_FOUND` "Strategy AST missing". A researcher
whose first strategy comes from a study met that 404 on their first export.

**An export on a thread with no strategy begins that strategy.** The EDA step
is the root, and it reaches WDK on the same commit, exactly as the agent's
first `create_step` does. Nothing in the EDA layer is special-cased:
`export_analysis_step` is unchanged, and the change is one guard removed from
`services/conversations/strategy_ops.py::apply_operation`.

**An export beside an existing strategy is unchanged.** `_apply_add_leaf` with
`AttachNewRoot` adds a second root, `primary_root_id()` keeps the existing
subtree, and `commit.py` builds the pushed AST from the primary root with
`include_detached=False`. The EDA step is persisted in `detached_roots` and is
not pushed. The tab presents it as a draft with an attach affordance.

**The three copies of the load became one.** `strategist_spec`, `jobs/runtime`
and `strategy_ops` each turned a `Conversation` plus a `ConversationStrategyView`
into a `PersistedStrategyGraph`, and the `strategy_ops` copy was the one that
demanded a `root`. `services/strategies/session_factory.py::persisted_graph` is
now the only one: an empty row carries no AST, and a present AST that does not
parse raises `StrategyAstCorruptError` (500, `ErrorCode.STRATEGY_AST_CORRUPT`,
detail naming the conversation and the pydantic reasons) rather than reading as
an empty strategy that the next commit would overwrite.

**An operation that needs a graph is refused by the op algebra.** Without the
blanket guard, `DeleteStepOp` on an empty graph reaches `apply.py::_require`,
which raises `ApplyError("step 's1' not found")`. That exception had no
handler, so it rendered as a 500. `platform/error_handlers.py::apply_error_handler`
now renders it as 422 `VALIDATION_ERROR`, title "Operation rejected", with the
op algebra's own message as the detail.

# What was rejected

**Disable the export button until a strategy exists.** It reads as a broken
button on the first thread a researcher opens, and it is wrong about the
product: the first strategy often comes from a study, not from a search. The
agent's own first step already takes the create-it path, so refusing the same
thing to the tab would have been two rules for one commit.

**Keep the 404 and special-case `AddLeafOp(attach=AttachNewRoot())`.** That
puts an operation-shaped branch in a function whose job is authorization and
loading, and it leaves the pre-existing 500 on every other operation against
an empty graph.
