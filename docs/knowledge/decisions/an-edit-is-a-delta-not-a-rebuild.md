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
  `SpecDiff`, the edited spec and the live graph, and returns
  `list[GraphOperation]`. The diff is the whole account of what moved - the
  values, the ones taken away (`removed_params`) and whether the criterion was
  put on another search (`rebound_search`) - so the spec the turn started from
  is not read a second time here. A criterion on a live step emits nothing when
  it is `kept`; when it is `changed` it emits `UpdateStepParamsOp` on its own
  step id, or `ReplaceSubtreeOp` when the diff reports a rebound search or a
  removed value, because an update merges. A `dropped` one emits `DeleteStepOp`
  with the resolution `operations/resolutions.py` computes.
- An operation carries ONLY what the diff says moved. The update sends the
  moved parameters and nothing else, so a value the researcher set on the
  canvas is not overwritten by the value the spec happens to state for another
  parameter of the same step. A restatement of the same search starts from the
  LIVE step's parameters, less the names the edit removed and plus the ones it
  moved; only a rebound search takes the spec's whole binding, because a
  different search shares no values with the one it replaces.
- The strategy decides which criteria the edit introduces, not the diff: a
  criterion the edited structure names that `graph.steps` holds no step for
  emits `AddLeafOp` plus `AddCombineOp`, or `AddTransformOp`, anchored on the
  step the after-structure puts it above, whatever disposition the diff gives
  it. A criterion an earlier dispatch framed and left for the user is in the
  baseline, so the diff calls it kept or changed and only the graph can say
  that the strategy has yet to build it.
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
one: a shape that leaves out a criterion the spec keeps, one that adopts a step
from outside the strategy under edit, one that leaves a step disconnected, and
one that takes a step running a search off the strategy while the edited spec
states no drop for it. A dropped criterion accounts for the step it names AND
the subtree under it, which is how one criterion stands for a saved strategy
the build expanded, so dropping that criterion is not a removal the edit failed
to state. The measurement of the first three is
`domain/strategy/stated_shape.py::stated_shape`, read twice: a wiring plan that
departs from the stated shape is planned again as a restructure, and the
restated plan is refused when it departs as well. The fourth compares the
planned graph against the steps the strategy reached when the turn began, which
is what tells a spec describing another strategy from an edit that adds to this
one. The edit path is one call site;
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
refusal. A criterion the graph holds a step FOR is never an option, whatever the
structure says: `fold_option_criteria` takes the live step ids, so a step the
structure has not caught up with is refused by the shape rule rather than
described to the model as a value to fold and drop.
`spec_fold.py::fold_option_criteria` is what puts its stated
values on that step: the build folds the spec before it mints the tree, and the
edit folds both sides before it measures the difference, because WDK holds an
option as a value in the search's own parameters. A value the carrier's own text
states holds; a value it defaulted or FRAME assumed is overridden, because an
assumption is the value the model chose and the option is the one the user
states. Each value the option moves is recorded as an assumed value whose reason
is the option's text and whose `carried_from` names the option, replacing any
assumption the carrier held for that name, so the step keeps its own name and
the constraints carry the user's choice rather than the model's guess. An option
that no single criterion in the structure carries is placed nowhere, and so is
one that restates a parameter an earlier fold already carried with a different
value, because two options stating one parameter of one step two ways is a
contradiction in the spec itself. A count from a
step that ignored a stated value is the harm this whole rule exists to prevent,
so the two seams that take a spec the model just wrote refuse both:
`build_strategy` and the new side of `run_edit`. The stored side of `run_edit` folds leniently, because a
refusal over a spec an earlier turn left is one this turn cannot satisfy.

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
"start over" goes through `clear_strategy`. It is one of the Lead's two
destructive tools. `delete_step` removes the step it names and whatever that
step's departure orphans: the combine above it, the secondary branch of a
combine under a transform, or, for a root that is not the strategy's own root
combine, the subtree under it. The root it measures against is the step the
strategy is cited with, which is the one root of a whole graph or the root the
last push made the WDK strategy's. It refuses two calls rather than guess: a
transform nothing can take the place of, at the root and under another
transform, and any root of more than one step on a thread that holds several
roots when no push says which is the strategy, because the largest component
is not the strategy's. A root of one step takes only itself, so it goes.
`clear_strategy` removes the whole strategy. The user approves either before
any step is removed. The Lead's `delete_step` and the building pass's are one
tool reading one set of rules, so no caller chooses how the tree is re-wired,
and the surface a refusal is written for changes only the way out it names.
`apply_operations` removes nothing: the operation union the model reads leaves
`DeleteStepOp`, `DeleteEdgeOp`, `ReplaceStrategyOp` and `ReplaceSubtreeOp`
out, and a batch that names any of them is refused whole. Each of the four
removes steps: an edge delete because a collapse takes the combine and the
step under its other slot, a strategy replacement because it keeps only the
tree it carries, and a subtree replacement because it drops the steps the new
branch does not carry. Three model-driven surfaces take steps off a strategy.
Two ask the researcher first: `delete_step` for one step, and
`replace_subtree` for one branch, which is also refused when the branch would
drop a criterion the spec states. The third, `create_eda_step` with
`replace_step_id`, replaces the named step's subtree without a card: the route
block the Lead reads names the one step the export supersedes, so the call
carries the researcher's own instruction, and the spec guard bounds what can
go. Whether that replacement should be gated like the other two is an open
decision, not settled here. The graph canvas still sends an edge delete,
through the HTTP route, and the commit path still replaces a strategy to
restore one; both read the wider union. The
third path, a spec edit, still resolves its own delete through
`operations/resolutions.py::compute_delete_choices`, and it answers two
reachable shapes differently from `delete_step`: a transform `delete_step`
refuses for want of an heir, which is the strategy's root or one under another
transform, and which the spec edit deletes on its own with the step it read
standing in its place, and a detached leaf root, which `delete_step` removes on
its own and the spec edit turns into a delete of the whole strategy. The
stated-shape guard stops both before a write. Which of the two answers is right
is the open decision.

A resolution the menu offers is one the apply performs: every surface reads
`compute_delete_choices` for what to offer and
`resolutions.py::why_the_graph_refuses_the_delete` for what the graph cannot
place, and the second states the rule that both the HTTP graph route and
`apply_operation` answer with. The re-wiring follows WDK's own `removeStep`:
the step goes and its primary input stands where it stood.

The delta the Lead reads carries its own account of what it built:
`EditDelta.added_step_ids` names the criteria the edit minted a step for,
computed by `spec_to_operations::criteria_the_edit_introduces`, and the same set
decides which steps a refusal of the values is blamed on. The diff cannot serve
for that: a criterion framed on an earlier turn is in the spec the diff compares
against, so it reads kept or changed while the strategy gains a step.

# Anchors

`domain/strategy/spec_to_operations.py`, `domain/strategy/edit_plan.py`,
`domain/strategy/stated_shape.py`, `ai/lead/edit_dispatch.py`,
`services/strategies/commit.py`.
