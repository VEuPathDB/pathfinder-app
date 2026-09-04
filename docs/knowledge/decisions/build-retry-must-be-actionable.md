---
type: Decision
title: A retry must be something the model can act on
description: build_strategy answered "call frame_problem first" when FRAME had already run and left open slots, sending the Lead round a loop only the user could break.
tags: [agents, error-messages, frame]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# What was wrong

`build_strategy` guarded with a single branch:

```python
if spec is None or not spec.ready_to_build:
    raise ModelRetry(
        "OperationalSpec is not ready to build (no criteria/structure, or "
        "open param slots need user input). Call frame_problem first."
    )
```

One message for two unrelated situations. Seen on a real multi-criterion drug-target build: FRAME bound **all 8 criteria** and left **7 open parameter slots** with `needs_user`. The Lead called build anyway and got told to run FRAME again -- which regenerates the same slots, because only the user can supply them.

A `ModelRetry` says "you can fix this yourself and try again". That is true when no spec exists. It is false when a human has to answer, and stating it anyway invites a loop.

# The fix

`build_not_ready_message(spec)` answers by case:

- **no spec, no criteria, or no structure** - "call frame_problem first", which the model can act on;
- **open slots** - names each parameter, carries FRAME's question and options, and says explicitly *do not re-frame, ask the user*;
- **unbound criteria** - names them and sends the model back to FRAME to bind;
- **criterion-level open params** - names them and says to ask.

The guard still raises `ModelRetry`; only the wording varies. That keeps the existing control flow while removing the instruction that caused the loop.

# What this did not fix

The turn that exposed it also died with an OpenAI `No tool invocation found for tool call ID` error. That crash **recurred on a re-run that never reached BUILD**, so it is independent and is tracked separately in the backlog. Fixing the message was worth doing on its own merits; it was not the crash.

# Anchor

`build_not_ready_message` in `ai/lead/sub_agent_dispatch.py`. Guarded by `tests/unit/ai/lead/test_dispatch_messages.py`, which asserts the open-slot message never says "frame_problem".
