---
type: Decision
title: The thread log is the EDA binding's history, and a branch never shares a document
description: Fork and revert read the newest data-eda.analysis-state part of the thread's own log and put the binding where it says, creating a document of the branch's own from the recorded descriptor. A binding revision table, copying the conversation_analyses row, and the service's copy route were rejected.
tags: [eda, branching, revert, persistence, thread-surgery]
generated: { by: claude-code/opus-5, at: 2026-08-31T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-31T00:00:00Z }
status: stable
---

# What was decided

`conversation_analyses` holds one row per thread: the site, the dataset, the
analysis the thread has open and a revision that grows on every authoring
mutation. `bind` replaces that row in place, so the row's `created_at` names
the first bind and its contents name the last: no cut on a timestamp can say
which analysis the thread had open at a chosen message.

**The log already answers that.** Every EDA authoring tool emits a
`data-eda.analysis-state` part carrying the site, the dataset, the analysis id,
the display name and the whole filter array, and
`analysis_state_chunks_if_changed` emits it whenever that state differs from
the one the thread last showed. `conversation_events` is durable, is cut by a
revert on `emitted_at` and is copied by a branch, so the newest surviving part
at or before a message is the binding state that message was answered against.
Fork and revert read it through one seam,
`services/eda/thread_surgery.py::newest_analysis_state`.

**A branch copies the descriptor, never the document.** Two threads authoring
one analysis document would each overwrite the other's subset, so the branch
creates an analysis of its own with the recorded display name and patches the
recorded filters onto it, using the same `open_analysis` and `patch_subset`
calls `open_eda_analysis` and `set_eda_filters` use. A branch whose copied log
holds no such part opens with no study, which is what its transcript shows.

**A revert puts the binding where the surviving log says**, in four cases: no
part and no row does nothing; no part with a row deletes the row, when the log
did record a binding before the cut; a part naming the bound analysis patches
its subset back when the live subset differs; a part naming another analysis
binds that one and patches its subset. Replacing a
binding does not delete the document it replaced - nothing in the application
calls the analyses client's `DELETE` - so the recorded id normally still
resolves upstream, and only a `404` makes the revert create a document from the
recorded descriptor. The case table is
[thread surgery invariants](../conventions/thread-surgery-invariants.md), F7
and R7.

**A thread whose log never recorded a binding is left alone.** The EDA tab's
own route (`PATCH /conversations/{id}/eda`) mutates the binding without
emitting a part, so a study opened from the tab alone is invisible to the log.
The revert therefore reads, before the cut, whether the log holds any
analysis-state part at all, and unbinds only when it does: the same shape the
strategy uses for a thread that predates the revision store. A thread that
mixes the two surfaces follows the newest part its log still holds, because
that is the last thing the transcript says about the study.

**A study service that refuses costs neither operation.** The EDA calls run
before the row is written, and an `AppError` from any of them is logged and
swallowed: the branch opens unbound, and the revert leaves the binding where it
was. A thread operation must not fail because a document nobody can reach.

**The revision counter restarts on a bind and grows on a refilter.** It orders
the writes of the two surfaces that edit one analysis, so a fresh document
starts at one and a restored subset is one more mutation.

**The card carries the document's stamp.** Every analysis-state part records
the `modificationTime` the service held on the document it was read from
(`EdaAnalysisState.modification_time`). The turn briefing names the open
analysis as changed after the card when the newest part shows another
document, a lower revision, or a stamp the service no longer holds, which is
how an edit made on the site reaches the Lead
(`services/conversations/thread_activity.py`). The service stamps to the
second, so two edits within one second read as one.

# What was rejected

**A stamp column on `conversation_analyses`, written at each bind and each
turn.** Every surface that mutates the document would have to write it beside
the revision, and a turn that ended on a mutation would read its own edit as
the site's on the next turn. The part is written by every surface that shows
the analysis already, so it needs no migration and no second writer.

**An append log of bindings keyed by the message the turn ended with**, the
shape the strategy uses. It is a migration and a second writer for state the
thread's own log already records part by part. The strategy needed its own
table because the log carries the chunks a turn emitted and not the AST a turn
persisted; the binding is the opposite case, because the analysis-state part
carries the whole binding state on the wire.

**Copying the `conversation_analyses` row into the branch.** Free, and wrong:
two threads would then author one analysis document, and the first filter the
branch sets would rewrite its parent's subset.

**The EDA service's `POST .../{analysisId}` copy route.** It copies the
document as it stands now, which is the state a branch point must not inherit,
and it gives the copy the parent's current subset rather than the anchor's. The
recorded descriptor is the anchor's, so create-then-patch is both correct and
one fewer upstream shape to depend on.

**Deleting the document a rebind replaces.** It would let a revert know the
recorded id is gone rather than discovering it, and it would destroy an
analysis the researcher can still open in the EDA tab. The `404` path covers
the case at no cost.

# What would falsify this

`apps/api/src/pathfinder/tests/integration/persistence/test_fork_case_matrix.py`
fails if a branch shares its source's analysis id, opens no document for a
recorded state, or fails when the study service refuses.
`.../test_revert_case_matrix.py` fails if a revert keeps a binding its deleted
turns opened, leaves a subset the deleted turns set, or fails on a refusal.
`apps/api/src/pathfinder/tests/unit/services/eda/test_binding_plan.py` fails if
the four cases stop mapping to the plan they name.
