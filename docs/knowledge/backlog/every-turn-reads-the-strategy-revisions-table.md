---
type: Backlog
title: Every turn reads strategy_revisions, including a turn of an assistant that has no strategy
description: The turn driver calls turn_start_revision_id on every turn and restore_pre_turn_strategy on every cancel, both PathFinder reads, so site_help pays a SELECT on strategy_revisions per turn and any future assistant inherits the same; the generic seam for work of that shape is already on the spec.
tags: [assistants, turn-runner, assistant-spec, strategies, generality]
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
status: stable
---

# What I did

Read the turn driver `apps/api/src/pathfinder/ai/conversation/turn_runner.py`
(396 lines) top to bottom and followed the two calls it makes that are not
about a turn.

# What I got

Line 179, before the start chunk and for every assistant:

```
pre_turn_revision_id = await turn_start_revision_id(body.conversation_id)
```

`services/conversations/turns.py:38` implements it as
`StrategyRevisionRepository(session).latest(conversation_id)`, a SELECT on
`strategy_revisions`. Line 229, on every cancelled turn, calls
`restore_pre_turn_strategy`, which opens a session and runs
`discard_turn_strategy_writes` on the same table.

Line 240 is the seam for exactly this shape of work:

```
if spec.turn_epilogue is not None:
```

`assistants/site_help/spec.py:112-119` declares no epilogue and the assistant
owns no strategy, yet its turns take the same read and its stopped turns the
same restore.

# Why that's wrong

A driver that names one product's table is a driver every later assistant
inherits: the cost is a round trip per turn today, and the rule is that any new
assistant must tolerate PathFinder's schema. It also splits the strategy
lifecycle across two places, so a change to what a stopped turn restores has to
be made in a file about turns.

# Why it happens

`_run_turn_with_context` calls `turn_start_revision_id` and
`restore_pre_turn_strategy` directly instead of through a declaration on
`AssistantSpec`.

# Fix

Library first, in `ai-assistant-platform`: give `AssistantSpec` the two seams
the epilogue is missing, a turn prologue that returns an opaque token and a
cancel hook that receives it, beside `turn_epilogue` in
`assistant_core/spec.py`. Then here: `build_pathfinder_spec` declares the two
reads, `turn_runner.py` drops both imports, and the app takes the seams at the
library's next tag. The epilogue alone cannot carry this: it runs after the
graph, takes only a conversation id, and cannot tell a stopped turn from a
finished one.

# What you'd get

A `site_help` turn makes no strategy query and a stopped `site_help` turn
restores nothing, while a PathFinder turn behaves exactly as it does now. The
turn driver names no product table.
