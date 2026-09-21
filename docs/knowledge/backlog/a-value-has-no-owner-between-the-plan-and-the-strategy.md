---
type: Backlog
---

# A value has no owner between the plan and the strategy

A criterion and the step it built share one address and count from one source. A
VALUE still has two holders: the spec states the term a frame bound and the step
holds the form WDK renders, and nothing says which one a turn believes. Two
defects come from it. Both are pinned by a strict `xfail` in
`apps/api/src/pathfinder/tests/unit/ai/lead/test_the_live_value_refresh_keeps_the_turn_whole.py`,
so the suite fails the moment either is fixed.

## 1. A value set on the canvas never reaches the spec

**What I did.** A built criterion binds `timepoint=40`. The researcher sets 48
on the step in the graph editor. The next turn runs the production refresh and
reads the thread's spec.

**What I got.** The step holds 48. The spec states 40
(`test_a_value_set_on_the_canvas_reaches_the_spec`: expected 48, got 40).

**Why that's wrong.** FRAME's workspace, the ledger and the Lead's reply
describe a strategy the researcher no longer has. A summary that names the
parameters of the strategy names a value the results were not computed with.
When the next edit moves a dependent parameter of that step, FRAME picks the
child from a sheet read under the spec's stale parent, and a child that is
valid under both parents takes the other parent's meaning without a refusal.

**Why it happens.** `Criterion.resolved_params` is written by a frame and by
nothing else. A canvas edit commits through
`services/conversations/strategy_ops.py::apply_operation`, which writes the
graph and never the spec, and the pre-turn refresh
(`ai/lead/pre_turn.py::refresh_live_strategy_state`) reconciles ids and counts
only.

**What was tried.** Copying every live step value into the spec on each turn.
It is withdrawn: the step holds the canonical form of a value the assistant
wrote (the leaf organisms under a branch term), so the copy replaced the term a
criterion states, and the next edit read an untouched criterion as moved. Two
tests in the same file pin that trap and stay green.

**Fix.** A canvas edit is an event this application owns. Record, at the canvas
commit and only there, which parameters of which step were set outside the
thread; the pre-turn refresh copies exactly those values into the criterion
before the turn baseline is recorded, clears the record, and leaves every other
value in the form the criterion states. A resumed parked dispatch applies the
same copy to its recorded baseline.

**What you'd get.** The spec states 48 at the next turn, the branch term
`Anopheles` is still `Anopheles`, and an edit of another parameter of the same
step sends only that parameter.

## 2. A change framed beside an open question is never pushed

**What I did.** One edit moves a built criterion's percentile from 80 to 90 and
adds a criterion with one open parameter. The edit ends `needs_user`. The next
turn answers the question.

**What I got.** The follow-up commits the new step. The percentile stays 80 on
the step, the diff calls that criterion "kept", and the reply says nothing
about it (`test_a_change_framed_beside_an_open_question_is_pushed_once_it_is_answered`).

**Why that's wrong.** The researcher asked for 90, was asked one question,
answered it, and holds a strategy computed at 80 with no sign that the request
was dropped.

**Why it happens.** `ai/lead/edit_dispatch.py::run_edit` returns `needs_user`
after `apply_agent_state` committed the draft as the thread's spec. The next
dispatch records that draft as `spec_before_dispatch`, so the moved value is
part of its own baseline.

**Fix.** The baseline an edit plans against is the last spec the strategy
answered to. A `needs_user` draft is a plan the strategy has not reached, so it
is kept as FRAME's workspace and as the restore target of a refusal, and it
does not become the planning baseline until a push, a build or a clear makes
the strategy answer to the spec again. An implementation of this shape was
written and reverted: it turns the diff's label for a criterion built from an
earlier plan from "kept" to "added", so the design must first decide that
`EditDelta.added_step_ids` and the diff's added count agree.

**What you'd get.** One commit carrying `updateStepParams` for the percentile,
`addLeaf` and `addCombine`, and a delta that reports changed 1, added 1.

## Before either fix

A regression net over the production seam (the pre-turn refresh, `run_edit`,
`run_frame`, the diff and the planner, faking only the sub-agent stream and the
commit) for every way the spec and the graph can disagree at a dispatch start.
`tests/unit/ai/lead/_disagreement_thread.py` and its two test modules are the
start of it. It must be green on the tree as it stands before the design moves
anything. One state has no test at any seam: a strategy edited on the VEuPathDB
site itself.
