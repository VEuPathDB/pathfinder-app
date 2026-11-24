---
type: Decision
title: A criterion and the step it built are one address, so the persisted AST is what an edit starts from
description: A build mints each step under the id of the criterion it states, and a thread with no spec reconstructs one from its persisted AST. Both give every criterion the id of the step it describes, which is what lets an edit address a step without a side table.
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
- `build_step_tree` mints every leaf and transform under its criterion's id
  (`node_for`), and a saved reference's cloned root under the id of the
  criterion that names it, so a spec FRAME authored with labels like
  `c1_protease_text` is already addressed by the steps the build makes. No
  record the turn holds is re-keyed, so an operator reading or any other
  criterion-keyed record stays on the criterion it was read for.

The consequence is the one the edit path needs: `operations_for` addresses a
step by the criterion id it already holds, with no side table to keep in step
and nothing to drift.

One address, two VALUE FORMS. The criterion states the term the request or the
model named; the step holds the form VEuPathDB took, and a tree parameter bound
to a branch term is submitted as its leaves
(`veupathdb/domain/parameters/wdk_vocab.py`). So a difference between the two
is not evidence of a change, and nothing copies the step's value over the
criterion's: a blanket copy replaced `organism=["Anopheles"]` with 41 leaf
names, which then read as a change the next edit pushed. What keeps a value
the researcher set on the canvas is the planner, not a copy: an edit sends only
what the diff says moved (see
[an edit is a delta](an-edit-is-a-delta-not-a-rebuild.md)).

What a value written OUTSIDE the thread means is settled separately: the thread
records the spec the strategy answers to and the tree it held, and plays what
moved since onto the spec, name by name, for the names the search's sheet shows
(see [the strategy answers to a spec](the-strategy-answers-to-a-spec.md)). That
is how a value the researcher sets on the canvas reaches the criterion without
a form ever being copied: the two trees are compared to each other, never a
tree to a spec.

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

A step id is a label a model wrote, such as `c_sp`, for every step a build made.
A combine the build makes, and every step under a saved reference's root, still
takes a fresh `step_` id; the criterion's `text` is the readable half and always
was.

**Re-keying every record onto the minted step ids** was the earlier form: the
build minted fresh ids and renumbered the spec. It kept two id spaces, and a
record keyed by criterion (an operator reading) went stale on every build.

# Anchors

`domain/strategy/spec_hydration.py`, `domain/strategy/spec_tree.py`
(`build_step_tree`, `node_for`), `ai/lead/sub_agent_dispatch.py`.
