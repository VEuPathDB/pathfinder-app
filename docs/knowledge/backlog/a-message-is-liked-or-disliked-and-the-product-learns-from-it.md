---
type: Backlog
---

# A message is liked or disliked, and the product learns from it

Release a15. "How PathFinder learns" is today the memory auto-write after a
verified turn. A researcher has no way to say a reply was good or bad, so a bad
turn writes the same case memory as a good one and no eval case comes out of it.

## What

A like and a dislike control on every assistant message, stored with the message
(`messages` metadata or a table beside it, one row per message per user, the
latest rating wins). Three readers:
- the memory auto-write writes no `case` from a disliked turn and pins the case of
  a liked one (the store already has a pin weight in the hybrid score);
- a disliked turn is staged as an eval case through `eval_staged_cases`, with the
  conversation id, the turn's request and the extract the devtools already build;
- usage telemetry carries the rating, so a run can be read by outcome.

## Constraints

No fine-tuning story. The rating is a fact about one message, never a global
weight on the model. The web control rides the message actions the thread already
draws; the API is one `PUT /conversations/{id}/messages/{message_id}/rating`.
Regression tests: the auto-write skips a disliked turn and pins a liked one; a
dislike stages one eval case; a rating changed twice leaves one row.
