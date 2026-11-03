---
type: Decision
title: A canvas edit is refused while a writer holds a tree
description: A turn reads the stored strategy once and writes its whole tree back, so an edit applied beside it is lost. The operations and insert-saved routes answer 409 while the thread lock is held, a turn is queued or running, or a durable task is active, and they apply under a parked approval, which holds no tree. Queueing the edit behind the turn, a compare-and-set on the row and refusing under a parked approval were rejected.
tags: [canvas, strategy, concurrency, threads]
generated: { by: claude-code/opus-5.5, at: 2026-11-03T00:00:00Z }
status: stable
---

# What loses an edit

`build_turn_context` reads the stored strategy once, when a turn starts. Each commit of that
turn writes the whole tree it holds (`services/strategies/persist.py`), and the strategy
write lock covers that write and not the turn's read. So an edit committed after the read
and before the write is gone, and the canvas was told 200.

The test for each state of the thread is whether a process holds a tree it will write back.

| State | `claim_settled_thread` | Holds a tree? | An edit |
|---|---|---|---|
| Thread lock held by a dispatch, a branch or an undo | `LOCKED` | the writer is about to start or is cutting the thread | refused |
| Turn queued or running | `TURN` | yes, or it reads one as the edit commits | refused |
| Durable task active | `TASK` | the body does not, and the turn it opens does | refused |
| Approval parked | `APPROVAL` | no | applies |

**A durable task refuses the edit because of the turn it opens.** No body under `jobs/impls/`
writes the strategy. But `assistant_core.tasks.runner` opens the completion turn inside the
durable job, so no `chat_turn` job names it, and the task's row stays active until that turn
ends. An edit that passes while the body runs can also commit after the completion turn has
read its tree.

**A parked approval does not refuse the edit.** The turn that parked has ended, so its job is
settled and nothing holds a tree. The answer opens a new `chat_turn` job, which takes the
thread lock to enqueue and reads the stored row when it starts, and
`pre_turn._answer_what_was_written_outside` plays the edit onto every spec the thread holds.
A yes on a card that removes steps acts on the steps the row holds then, as the researcher
asked. A refusal here would also hold the canvas for as long as a card waits.

`claim_settled_thread` stays the one definition of busy. It names an active task ahead of a
parked approval, so `APPROVAL` means that nothing else holds the thread.

# How the claim is held

`refuse_an_edit_on_a_busy_thread` runs on the session that holds the strategy write lock, in
the same transaction, and before the edit saves a dataset or reads the site. Each consequence
follows from that:

- **Two edits do not refuse each other.** The second waits on the strategy write lock, and
  both locks end when the first commits.
- **A refused edit leaves nothing claimed.** Advisory transaction locks end with the
  transaction, on a commit or on the rollback that a refusal raises.
- **A message waits for the edit.** `hold_thread` in the dispatcher waits for the thread lock,
  so no turn reads the tree an edit is about to replace. A site that does not answer within
  `HOLD_WAIT_SECONDS` makes the message a 409.
- **There is no deadlock with a branch or an undo.** Those take the thread lock first and may
  then wait on the strategy lock, and the edit only tries the thread lock, so it is refused.

# What other routes do

`POST /conversations/{id}/insert-saved` reads the stored tree and writes it whole, so it takes
the same refusal. The EDA export reaches `apply_operation` and takes it there.

`POST /conversations/{id}/refresh-counts` is not refused. It stores only what the site answers,
and the researcher's edit is not among it. A turn that commits after it writes the counts it
holds, and the next refresh reads them again. A rename through `PATCH /conversations/{id}` is
not refused, because the thread owns the name and the tree holds a copy. That route no longer
takes a tree: nothing sent one, and a tree written there held no lock and passed no check.

# What was rejected

**Queue the edit behind the turn.** The queue would apply an edit to a tree the turn has
changed, minutes after the researcher made it, with nobody watching the outcome. The card the
canvas draws would show a state the server does not hold in the meantime.

**A compare-and-set on the stored row.** It moves the failure to the turn's commit, so the
turn loses its build to an edit and has to explain that to the researcher.

**Hold the strategy write lock across a turn.** A turn runs for minutes, and every read that
takes the lock would wait for it.

# What the canvas does

The web app has no gate on a running turn: `useApplyOperation` sends from every canvas action,
whatever the turn's state. The refusal reaches the researcher as the toast `toUserMessage`
reads from the problem detail. `onMutate` runs before a queued mutation takes its place in the
scope, so a second edit's snapshot can hold the first one's optimistic state. So a failed edit
takes its own entry off the undo stack, gives back the redo stack its push cleared unless a
later edit stands on it, and reads the strategy again after its rollback.
