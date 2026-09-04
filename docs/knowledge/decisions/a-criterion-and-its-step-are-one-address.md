---
type: Decision
title: A criterion and the step it built are one address, so the persisted AST is what an edit starts from
description: A build re-keys the spec on the step ids it minted, and a thread with no spec reconstructs one from its persisted AST. Both give every criterion the id of the step it describes, which is what lets an edit address a step without a side table.
tags: [agents, strategy, wdk, graph-ownership]
generated: { by: claude-code/opus-5, at: 2026-08-28T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-28T00:00:00Z }
status: stable
---

# The decision

`Criterion.id == StrategyStep.id` for every spec that describes a strategy that
exists. Two paths hold it up:

- `spec_from_ast` keys each reconstructed criterion on the node's own id, so a
  thread the graph editor or a saved-strategy import produced addresses its own
  steps.
- `build_step_tree` mints an id per node and reports that mapping, and
  `build_strategy` writes
  `renumber_criteria(spec, mapping)` back into the state, so a spec FRAME
  authored with labels like `c1_protease_text` adopts the step ids the build
  produced.

The consequence is the one the edit path needs: `operations_for` addresses a
step by the criterion id it already holds, with no side table to keep in step
and nothing to drift.

For an edit turn the persisted AST is the truth about what the strategy is, and
the spec is a view derived from it. The spec keeps its role as the artifact
FRAME writes; it stops being an independent memory of values that WDK and
Postgres already hold. That is why the hydration copies `node.parameters`
verbatim and never re-derives them.

# The alternative that was rejected

**Add `step_id: str | None` to `Criterion` and `StructureNode`.** More explicit,
and it carries new state that can disagree with the id beside it. Both types
serialize into the ledger data part, so it also costs a `yarn generate:types`
run and a frontend regeneration for a field that only restates an id.

# What it costs

A criterion id is no longer a label a human reads. The model still names one on
a fresh frame, and it is replaced the moment the build gives it a step. Anything
that displayed a criterion id as prose shows a step id after the first build;
the criterion's `text` is the readable half and always was.

# Anchors

`domain/strategy/spec_hydration.py`, `domain/strategy/operational_spec.py`
(`build_step_tree`, `renumber_criteria`), `ai/lead/sub_agent_dispatch.py`.
