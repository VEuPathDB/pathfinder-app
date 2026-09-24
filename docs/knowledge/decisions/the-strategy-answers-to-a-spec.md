---
type: Decision
title: The strategy answers to a spec, and what moved since is replayed onto it
description: The thread records the last spec the strategy was made to answer to and the tree it held at that moment. Everything between that tree and the live one was written outside the thread, and it is played onto every spec the turn holds. An edit is planned against the answered spec, so a plan may run ahead of the strategy without becoming its own baseline.
tags: [agents, strategy, wdk, graph-ownership]
generated: { by: claude-code/opus-5, at: 2026-09-21T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-23T00:00:00Z }
status: stable
---

# The decision

The graph owns what the strategy IS. The spec owns what was SAID. Spec values
and graph values are different forms and are never compared to each other
([one address, two value forms](a-criterion-and-its-step-are-one-address.md)).
Two recorded facts join them, both on `StrategyDomainState` and both
checkpointed:

- `answered_spec`: the last spec the strategy was made to answer to.
- `answered_graph`: the tree it held at that moment, as
  `StrategyGraph.to_strategy_ast()` produces it with no sync state, so it
  carries searches, parameters, operators and wiring and no WDK id, count or
  validation.

One writer records both, `ai/lead/answered_strategy.py::the_strategy_now_answers_to`,
called by every path that makes the strategy state what the spec says: a build
(also a partly failed one, because the whole local tree persists), a pushed
edit including the return that finds nothing to push, the Lead's `delete_step`
and `clear_strategy`, an EDA export, and the hydration of a thread that holds a
strategy and no spec.

Everything between `answered_graph` and the live tree was written outside this
thread. `domain/strategy/outside_changes.py` reads it graph against graph, and
`domain/strategy/spec_replay.py` plays it onto every spec the turn holds, at
turn entry, whatever opened the turn - a fresh message, a resumed call or a
finished background task:

- a step the strategy lost takes its criterion out;
- a step it gained is stated, with the parameters its search's sheet shows;
- a value or a search moved outside is the researcher's statement, so the
  criterion takes it and everything it said about that name retires with it:
  the open slot, the default, the assumption a fold carried, the alternatives
  and the spec-level open slot;
- when the shape derived from the two trees differs, the built part of the
  structure is the strategy's own; a criterion the plan states and no step
  answers is re-joined at the plan's root combine when that is where the plan
  put it, and any other plan is left alone with today's refusal and its way
  forward.

Only names the search's sheet shows are replayed. A step carries WDK's own
parameters too, and a criterion states none of them.

**The site writes the strategy too.** A value, an operator or a step the
researcher changes on VEuPathDB itself is not in the stored graph until
something reads it back.
`services/strategies/site_changes.py::take_what_the_site_holds` reads the WDK
strategy and writes onto the stored graph what the site moved, graph against
graph: a value the site holds in neither form the step holds it in (its wire
string and its decoded value), a weight when the graph holds one, a set
operator, and, when the graph's whole main
tree is on the site, the site's tree, so a step removed there leaves, a step
added there joins with its decoded values, and a step replaced by another
search is replaced. All three entry points read the site under the thread's
write lock before they act. The turn entry
(`site_changes.py::read_the_site_into_the_thread`, called from
`ai/lead/pre_turn.py`) reads the stored graph again inside the lock, persists it
when the site moved it, and hands the turn that graph before
`the_changes_written_outside` runs, so a site edit is an ordinary outside change
the spec replay already handles; the lock is released before the model runs.
The canvas commit (`strategy_ops.apply_operation`) reads it before it plans the
edit, and the count refresh (`strategy_ops.refresh_counts`) takes the site's
values from the same read that supplies the counts. None of them writes a spec.
A site that does not answer writes nothing: the turn and the canvas edit go on
over the stored graph, and the refresh refuses with 503.

**The operator is the researcher's, as well as the terms.** What was SAID
includes how the requirements join. A `combination` constraint records one
operator over the researcher's phrases, and the message must carry both
(`domain/strategy/constraints.py::read_combination`): each term is located in
the message, and the text between two consecutive terms, in message order, is
the connective. A connective with "or" (or "and/or") states OR; one with "and",
"with", "plus" or "as well as" states AND; a bare comma or no text takes the
next conjunction in the list, and AND when none follows, OR when the list opens
with "either". An "or" inside one term's span is an alternative within that
requirement and never a connective. A message that names a "union" or an
"intersection" states that operator. `classify_user_intent` refuses a
combination whose terms the message carries and whose operator it does not,
and the refusal quotes the connective between the two terms.

An edit is planned against `answered_spec`
(`ai/lead/edit_dispatch.py::run_edit`). FRAME's declaration check, its work
order and the restore target of a refusal stay `spec_before_dispatch`, the plan
the dispatch found. A pass that ends `needs_user` leaves both answered facts
alone, so the value it moved on a built criterion and the criterion it framed
are still this edit's to push when the follow-up answers the question. The
planning diff is the delta the reply is read from, so
`diff.added_count == len(added_step_ids)`; a disagreement is refused with the
repair, never asserted.

**A push carries only what a pass of this turn accounted for.** The difference
between the answer and the plan, `diff_specs(answered_spec,
spec_before_dispatch)`, is what an earlier pass of this thread stated and no
push has applied: a drop, a moved value, a criterion with no step. The edit
work order names each of them, and the pass states a disposition for each in
its `changes`: repeating it lets it stand, and stating the criterion the
strategy holds takes it back. The word has to agree with what the pass
drafted - a criterion it calls dropped is one its draft leaves out, and any
other word is one its draft states - because two statements about one step
account for neither. A pending change no pass of this turn accounted for is a
refusal that names it, so a drop the researcher asked about and then took back
is never pushed by the turn that takes it back, and it is never lost in
silence either.

An OPTION is the request as much as the criterion that carries it. A value the
carrier only holds because the strategy answers to it moves when an option
states another; a value the carrier states of its own does not, because two
statements in one pass are a contradiction the carrier wins
(`operational_spec.py::_carry_the_option`).

**An analysis criterion states meaning, and the graph holds its document.** An
exported EDA step is a criterion whose `analysis` binding says what it selects
and whose `resolved_params` is empty
([an EDA analysis is a criterion of the spec](an-eda-analysis-is-a-criterion-of-the-spec.md)).
The replay reads a moved analysis step through `services/eda/export.py::exported_analysis`
into a fresh binding; `outside_changes` still compares the
two trees, document against document, so no spec value is compared to a graph
value. A criterion that waits for its analysis has no step, so
`the_strategy_now_answers_to` records the spec without it and the plan keeps
it, the way a plan may run ahead of the strategy.

A thread that has recorded no answer takes one: the spec its last dispatch
found when the plan runs ahead of it, otherwise the plan, in both cases without
the criteria its structure names and the strategy holds no step for. Nothing is
replayed that turn, because what moved before the first record is not
attributable to anyone. One code path, no flag, no migration.

# The alternative that was rejected

**A fingerprint into the revision log.** Record
`strategy_revision(graph)` beside the spec and read the answered tree back from
`strategy_revisions`. A fingerprint is not the address of a tree: it leaves step
ids out, so a step deleted on the canvas and re-added with the same search and
values reads as no change at all. The row is also not guaranteed to exist - a
swallowed persist, a duplicated conversation, a stopped turn that deletes rows,
and every thread whose last write predates the log - and neither "oldest" nor
"newest" row for a fingerprint is the answered one in general. The tree in the
state needs no row, travels with a fork's copied checkpoint, and self-heals
after a swallowed persist, because the next turn replays the spec back to what
Postgres holds.

**Letting VERIFY re-read the sentence for the operator.** VERIFY checks the
built tree against the recorded constraint, so a wrong operator recorded at
classification is one it confirms: the build that followed the recorded OR was
verified against the same OR. The operator has to be right where the
constraint is recorded, and the check there is the message's own connective.

**Recording hand-edited parameter names at the canvas commit.** It needs a
column the API process writes and the worker clears, and it misses operators,
searches and every other writer that is not the canvas.

**Copying live values into the spec every turn.** Withdrawn once already: the
step holds the canonical form of the term the criterion states, so the copy read
a submitted form as a change.

# What it costs

Four specs in the state instead of two. None is derivable from the others:
`operational_spec` is the plan FRAME writes, `answered_spec` is what the
strategy answers to, `spec_before_dispatch` is what a dispatch found and
restores to, and `spec_before_turn` is what the ledger diffs the turn against.
Each blob gains one spec and one tree, which is small beside the searches the
same state already holds.

The graph owns the built shape, so a join a plan restated and never pushed is
lost when the researcher also edits the canvas. A thread that recorded no
answer keeps, for that one turn, a criterion whose step the researcher deleted
before the upgrade; the edit that follows accounts for adding it back rather
than doing it silently.

# What it replaced

`spec_reconciled_with_graph` decided "did this criterion ever answer to a step"
from the last build outcome and from the shape of a minted step id. Both
heuristics are gone with it, and so are the refusal and the FRAME rule that
kept the model from naming a criterion `step_` plus eight hex characters.
`dispatch_context::_reconcile_the_parked_record` is gone too: the replay runs on
a resumed turn like any other.

# Anchors

`ai/graph/state.py` (`answered_spec`, `answered_graph`),
`ai/lead/answered_strategy.py`, `ai/lead/pre_turn.py`,
`domain/strategy/outside_changes.py`, `domain/strategy/spec_replay.py`,
`services/strategies/site_changes.py`,
`domain/strategy/spec_hydration.py::spec_stating_the_live_tree`,
`ai/lead/edit_dispatch.py`,
`domain/strategy/analysis_binding.py`,
`domain/strategy/constraints.py::read_combination`,
`ai/lead/intent.py::unstated_operator_refusal`,
`tests/unit/domain/strategy/test_combination_operator_is_stated.py`,
`tests/unit/ai/lead/test_classifier_reads_the_stated_operator.py`,
`tests/unit/ai/lead/test_the_strategy_answers_to_a_spec.py`,
`tests/unit/ai/lead/test_a_site_edit_and_the_next_edit.py`.
