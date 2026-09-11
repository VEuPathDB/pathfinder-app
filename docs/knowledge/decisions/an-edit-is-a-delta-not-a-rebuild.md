---
type: Decision
title: An edit turn is a batch of graph operations over the live strategy, never a rebuild of it
description: The Lead's `edit_strategy` dispatch computes a spec diff, turns it into `GraphOperation`s and hands them to the existing commit pipeline, so an untouched step keeps its WDK id and its hand-edited values. `build_strategy` refuses a thread that already has a strategy.
tags: [agents, strategy, wdk, graph-ownership]
generated: { by: claude-code/opus-5, at: 2026-08-28T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-01T00:00:00Z }
status: stable
---

# The decision

An edit does not produce a tree. It produces the smallest batch of operations
that turns the strategy the turn started from into the one the request asks for.

- `domain/strategy/spec_to_operations.py::operations_for` takes the computed
  `SpecDiff`, the two specs and the live graph, and returns
  `list[GraphOperation]`. A `kept` criterion emits nothing. A `changed` one
  emits `UpdateStepParamsOp` on its own step id, or `ReplaceSubtreeOp` when the
  search name changed or a value was removed, because an update merges. A
  `dropped` one emits `DeleteStepOp` with the resolution
  `operations/resolutions.py` computes. An `added` one emits `AddLeafOp` plus
  `AddCombineOp`, or `AddTransformOp`, anchored on the step the after-structure
  puts it above.
- A structure the live wiring does not hold - a re-nesting of the steps that
  stay, or a transform moved onto another input - is planned again as one
  `ReplaceSubtreeOp` at the strategy's root. The restated tree reuses the step
  id of every leaf, and of every combine whose ordered input pair the new shape
  leaves alone; the push planner diffs trees, so the unchanged leaves are
  skipped and only the combines are recreated.
- `ai/lead/edit_dispatch.py::run_edit` reads the strategy revision before FRAME
  runs, refuses the commit if it moved, and hands the batch to
  `services/strategies/commit.py::apply_operations_and_commit`, which patches
  only the steps whose inputs changed and re-PUTs the step tree only when the
  topology changed.
- `build_strategy` refuses a thread whose graph has steps.

The operations are planned against a working copy of the graph and applied to it
as they are planned, so each anchor is read from the state the earlier
operations left. An edit the algebra cannot express raises `UnsupportedEditError`
and the dispatch turns it into a `ModelRetry`; nothing is approximated.

# What it addresses

A measured run asked to add one transform at the end of a three-step strategy.
The turn re-framed, rebuilt every step, changed all four WDK step ids, orphaned
the previous three server-side, and put a hand-edited
`min_expression_percentile` back from 90 to 80 without saying so. A second
measurement on the real 15-node thread showed a rebuild of a reconstructed spec
preserving 0 of 15 step ids.

# The alternatives that were rejected

**Keep building, but carry criterion ids onto the nodes.** That makes a rebuild
id-preserving, and it is still a rebuild: `_replace_graph_contents` clears the
graph, so anything the researcher added on the canvas that the spec does not
describe is gone, and every step is re-pushed whether it changed or not.

**A `mode="edit"` flag on `frame_problem`.** Rejected: the precondition (a
non-empty entry spec), the revision guard and the diff gate all become
conditionals inside one function, and the Lead can pick the wrong mode
silently. A separate tool states the distinction in the tool list.

**Let the model call `apply_operations` itself.** It already exists and the
graph editor reaches the same pipeline over HTTP. Rejected because it asks the
model to author the operation algebra from a sentence; the diff already knows
what changed, and the algebra is derived from it rather than typed.

# What it costs

The mapping is not total. Four shapes are refused, and the refusal names which
one: a shape that leaves out a criterion the spec keeps, one that names a step
the strategy does not hold, one that adopts a step from outside the strategy
under edit, and one that leaves a step disconnected. The measurement is
`domain/strategy/stated_shape.py::stated_shape`. The edit path is one call site;
the `replace_subtree` tool is the second, measuring the same shape on a copy of
the graph and refusing the write with a `ModelRetry` naming the criteria it
would drop; `apply_operations_and_commit` is the third and the one no caller can
go around, holding any batch that replaces a subtree to the criteria the turn's
context carries in `stated_criteria`. A criterion whose step a `delete_step`
removed leaves the spec with it, so the criteria and the steps stay in one
address space. A criterion that states a step holding no other stated step
addresses that whole subtree, so a strategy built over a saved one is not
refused for the leaves the expansion brought, whether or not a combine wraps
the expansion. A step `create_eda_step` wires into the main tree is stated as a
criterion of its own, so an analysis exported into a strategy is measured like
any other step rather than as a step no criterion states.

Only the criteria that answer to a step are measured
(`stated_shape.py::criteria_with_steps`): the ones the strategy holds a step for
before the edit, plus the ones the edit mints a step for. All three call sites
state that second set the way each one knows it - the edit path from the
criteria the edited structure names, the two write paths from the step ids the
graph gains once the operations apply - so a batch that adds a criterion's leaf
and combines it applies instead of being refused for a step no criterion states.
A criterion in neither set binds an option on another criterion's search, so the
step carrying that search states it and it has no step of its own; it is never
planned as a change or a delete, never reported lost, and never named in a
refusal.

The same choke point holds a second invariant, which needs no spec: a write into
an input slot never overwrites the step that slot holds off the tree. Each
`AddLeafOp` into a slot and each `WireInputOp` records the step it displaces, and
a batch that leaves one of them unreachable and undeleted is restored and
refused. A rewire that puts the displaced step under the step replacing it is
what an edit emits when a new criterion joins an existing branch, so it applies.
`create_eda_step` refuses an occupied slot before it builds anything, naming the
slot, the step that holds it and the criterion that step answers.

A restructure also gives up the record class stored on each step, because
`ReplaceSubtreeOp` carries nodes; the next push assigns it again from the
catalog.

`build_strategy` is now unreachable on a thread with a strategy, so a genuine
"start over" goes through `clear_strategy`, the Lead's one destructive tool,
which the user approves before any step is removed.

# Anchors

`domain/strategy/spec_to_operations.py`, `domain/strategy/stated_shape.py`,
`ai/lead/edit_dispatch.py`, `services/strategies/commit.py`.
