---
type: Decision
status: accepted
supersedes: no-checkpoint-truncation.md
---

# A saved conversation outlives the build that saved it

## Decision

The state a conversation keeps between turns is rebuilt by the build that resumes it. A field
the resuming build no longer declares is dropped. Every field it still declares is rebuilt as
its model at the turn's entry (`ai/graph/rebuild.py`). A value the build cannot read ends the
turn with one sentence the researcher can act on ("This conversation was saved by an earlier
version of PathFinder and cannot be continued. Start a new conversation; the strategy and gene
sets it built are still yours."), never with an attribute error from the middle of a turn.

## Why

A researcher builds a strategy over days. An update that renames something inside the saved
state must not end that conversation, and when it truly cannot be carried forward the
researcher must be told so in plain words. The previous rule (strict state, checkpoints
truncated on deploy) assumed its refusal was loud; it was not: the checkpoint serializer catches
the strict model's refusal, constructs the state without validation, and the turn fails later on
the first nested record it touches. Two field renames shipped in one day without the truncation
the rule required, and every earlier conversation on the development database died that way.

## Rejected

- **Strict state plus a checkpoint truncation per shape change.** It destroys every conversation
  on each such deploy, and the refusal it promises is not the one the researcher sees.
- **An alias for each renamed field.** The compatibility path this project does not carry; a
  dropped field is dropped.

## Consequence

A field that changes its type keeps its name and must read the old value or default it. A renamed
field is a dropped field plus a new one, and its old value is gone after the next turn.
