---
type: Decision
title: The combine sentinel is a boundary default, not a kind flag
description: __combine__ stays in the persisted AST because searchName is required there, and every reader that used to ask it "is this a combine" now derives the kind from the node's inputs.
tags: [strategy-graph, wdk-alignment, graph-ownership]
generated: { by: claude-code/opus-5, at: 2026-09-01T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-01T00:00:00Z }
status: stable
---

# The decision

`StrategyStepNode.search_name` is required, and a set operation is not a WDK
question, so the persisted AST gives a combine the placeholder `__combine__`.
That placeholder is produced only inside
`veupathdb-py: src/veupathdb/domain/strategy/`: the model
validator that stamps a two-input node with no name, `rebuild_tree`, which
projects the keyed graph back to the persisted shape, and the two spec
translators, which mint a combine node whose inputs travel in the operation
rather than in the node.

Nothing reads it to decide what a step is. `StrategyStep.kind` comes from the
node's inputs, and `own_search_name` is the one place that translates the
placeholder back to "this step names no question of its own". The predicate the
push and validation paths need is `runs_a_wdk_search`, beside it. Two sites in
`apps/api/src/pathfinder/ai/` still compare against the constant, and both compare a search *name* a
model or a tool result supplied rather than a node: the step renderer, which
keeps the placeholder out of a line the model reads, and the variant guard,
which refuses a variant that names a combine.

The name never crosses the WDK wire. `WDKStepTree` carries step ids only
(WDK-STRAT-001), and a boolean step is created through `create_combined_step`
with the operator as a parameter (WDK-STEP-002, WDK-STEP-006), so
`push_step_to_wdk` branches on `StepKind.COMBINE` before the search name is
ever used.

# The alternative that was rejected

**Make `search_name` optional on `StrategyStepNode` and delete the constant.**
It is the shape the flat model already has, and it would leave one
representation of "no search". It was rejected because `StrategyAst` is the
persisted column and the OpenAPI response: every stored conversation, every
revision snapshot and the generated TypeScript would have to change together,
for a field that carries no information the inputs do not already carry.

# What it costs

A combine that loses an input slot round-trips as a transform whose name is the
placeholder, because the persisted AST states no kind. `runs_a_wdk_search`
answers "no" for it, which is why a half-wired combine is skipped rather than
validated against a search that does not exist. The canvas keeps that node so
the researcher can rewire it, and `pushable_root_id` walks past it
(WDK-STEP-004).

A combine imported from WDK keeps the real boolean question name WDK gave it,
so `own_search_name` returns that name rather than `None`. Both halves of the
translation are pinned by a fixture round trip.

# Anchors

`veupathdb-py: src/veupathdb/domain/strategy/ast.py` (`COMBINE_SEARCH_NAME`, the
validator default),
`veupathdb-py: src/veupathdb/domain/strategy/graph_model.py` (`own_search_name`,
`rebuild_tree`, `wdk_search_name`, `runs_a_wdk_search`),
`apps/api/src/pathfinder/tests/unit/domain/strategy/test_graph_model.py`,
`apps/api/src/pathfinder/tests/unit/domain/strategy/test_ast_persistence.py`.
