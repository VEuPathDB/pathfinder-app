---
type: Decision
title: A rating is a fact about one message, kept in a table of its own and consulted on every later memory write
description: A like or a dislike is a row in `message_ratings`, one per message per user, and the latest rating wins. It gates the case memories that message wrote (a dislike takes them out of the store and keeps their values on the row, a like pins them), stages a disliked message as one eval case cut at that message, and reports the rating with the turn's usage. The runtime's `messages` row, a memory kind, a flag, a tombstone and a global weight were all rejected.
tags: [memory, evals, feedback, persistence, telemetry, chat]
generated: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
status: stable
---

# What was decided

A researcher can like or dislike any assistant message. The rating is a row in
`message_ratings` (`persistence/models.py::MessageRating`), unique on
`(message_id, user_id)`, written by `INSERT ... ON CONFLICT DO NOTHING` and a
locked read, so a rating changed any number of times leaves one row with the
latest value. `rating` is NULL until the researcher rates, because the turn's
finalize creates the row first to list the case keys the message wrote.

The row has a foreign key to `messages` with `ON DELETE CASCADE`: a revert that
deletes the message deletes its rating, because a rating of a message the thread
no longer shows governs cases nobody can see or clear. A branch copies no
rating; it is a new thread and nobody rated its messages.

## The timing rule

The memory auto-write runs in `finalize_turn`, before the action bar appears, so
a rating always arrives after the fact. Two things follow:

- **The rating acts on the store after the fact.** `PUT` and `DELETE`
  (`services/conversations/message_ratings.py`) bring each case key of the
  message into the shape its deciding rating asks for
  (`domain/message_rating.py::settle_cases`): a dislike deletes the case from
  the store and keeps its value in `withheld_cases`, a like puts it back with the
  `pinned` tag the runtime's hybrid score reads, a clear puts it back unpinned.
  The withheld values are written before the store changes and trimmed after,
  so no failure between two steps loses a case value.
- **Every later auto-write consults the standing rating.** The case key is the
  content hash, so a later turn that reaches the same case writes the same key.
  `write_turn_memories` partitions the candidates
  (`domain/message_rating.py::partition_cases`): the message's own rating
  decides first, then the most recently updated rating of another message that
  lists the key. A withheld case is recorded on the message's row, so its own
  like or clear can put it back.

Both writers of one row hold `rating_lock(message_id)`, the advisory-lock
pattern of `strategy_write_lock`, in a session of its own so each step commits
on its own. It serializes a rating given while a durable task runs with the
continuation's finalize, which writes the same message.

## The two other readers

- **A dislike stages one eval case** (`services/eval_data/rated.py`) through the
  existing queue, for consenting users only. The extract is the thread cut at
  the last log row of that message, with the strategy snapshot in force at it,
  so the disliked turn is `extract.turns[-1]` and `EvalExtract` did not change.
  No verification verdict is required: a disliked turn that never verified is
  the case a curator wants. The row carries `rated_message_id`; the old
  one-row-per-thread index became two partial unique indexes (one extraction row
  per thread, one rated row per message), and promotion nulls the message id
  under the same check constraint as the user and the thread. A like or a clear
  deletes the staged row. The default expectation of a rated row compares
  nothing, and promotion without an explicit expectation is refused, because
  the recorded run is the one the researcher said was wrong.
- **The rating is reported** as the `product.message_rated` event through the
  existing product-action channel, emitted by the server after the commit, with
  the rating (or `cleared`), the message id, the turn's trace id, its tokens and
  its cost read from the message row.

# What was rejected

**The rating on the runtime's `messages` row.** A durable continuation
overwrites the row's metadata wholesale, so a rating given while a task runs is
erased; one JSON per message cannot hold one rating per user; the metadata model
is private to the runtime; and it would put a runtime release on the path of a
fact only this product reads.

**A rating as a memory kind.** A kind is recall material the model reads. A
rating is a gate on what the model recalls, and the model should not recall it.

**A global weight or a fine-tuning signal.** The rating is a fact about one
message. Nothing here changes a prompt, a model, a tier or a score outside the
cases that message wrote.

**`auto_retrieve=False` instead of a delete.** FRAME's `search_memory` does not
read the flag, so a disliked case would still reach the agent that binds
searches.

**A runtime tombstone for a dislike.** A tombstone cannot be removed, so a clear
or a flip to like could not bring the case back.

**A `pinned` field on the runtime's `MemoryValue`.** The runtime's score reads
the tag; a field would be a second pin representation. The tag enters the
embedded string, which shifts a pinned case's vector by one token; accepted.

**A separate table of turn case keys, or recomputing the keys at rating time.**
The rating row already exists per message; a checkpoint walk in the api process
is a second derivation of what the finalize already knew.

**The rating in the events snapshot.** The snapshot is the runtime protocol's
shape. The thread reads its ratings back through `GET .../ratings`.

**The browser emitting the telemetry.** Two calls per click could disagree with
the stored row; the server emits once, after the commit.

**One staged row per thread, marked with the disliked turn.** Two disliked
messages on one thread would share one case, and clearing one would delete the
other's.
