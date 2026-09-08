---
type: Backlog
title: The SSE golden depends on when the title task finishes
description: The position of the data-conversation-title chunk inside a turn is a scheduling outcome, so the golden simple-turn fixture pins an order the runner does not guarantee; a slower title task moves the chunk and fails the test without any product change.
tags: [chat, sse, testing, flaky, turn-runner]
generated: { by: claude-code/fable-5.1, at: 2026-09-08T00:00:00Z }
verified: { by: claude-code/fable-5.1, at: 2026-09-08T00:00:00Z }
status: open
---

# What is wrong

`ai/conversation/turn_runner.py` emits `data-conversation-title` from `_handle_custom`
on the first custom chunk that arrives after the title task reports done. The chunk
therefore lands wherever the title task happens to finish relative to the turn's
status chunks. The golden fixture
`tests/integration/chat/_fixtures/chat_sse_golden_simple_turn.json` records one such
position ("after Recalling earlier work" on the machine that recorded it on
2026-09-08; the previous recording had it after "Thinking..."), and
`test_chat_sse_golden_snapshot_simple_turn` asserts the whole list in order.

The suite treats a flaky test as an app bug, and this one is: the wire order of a
chunk that a client reconciles by kind should not depend on scheduling.

# Done when

Either the runner emits the title at a defined point of the turn (for example right
after `start`, or right before `finish`, with the title task awaited there), and the
golden is re-recorded once against that rule, or the golden compares the title chunk
by presence and payload rather than by position. The first is the product fix.
