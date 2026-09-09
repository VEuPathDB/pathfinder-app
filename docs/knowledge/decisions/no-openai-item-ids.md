---
type: Decision
title: Do not echo OpenAI item IDs back when you rewrite history
description: The Responses API validates every item ID you return, and our history processors mean the IDs never match. A real server-side rejection - but NOT the crash users see on branching, reverting and cancelling, which was misattributed here and is corrected below.
tags: [agents, openai, message-history, crash]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# Correction, recorded before the rest

The claim below that this fixes the user-visible crash is **wrong**, and the
sentence "the string is OpenAI's" is **wrong**. The string
`No tool invocation found for tool call ID "call_..."` is thrown by the Vercel
AI SDK *client*, in `ai/dist/index.mjs`, when a `tool-output-error` chunk names
a tool call the client never saw announced. It never reaches a backend log,
which is why it looked like a silent provider rejection.

OpenAI does reject echoed item IDs, and `openai_send_reasoning_ids=False` is the
right setting for that. Two failures with nearly identical wording were
conflated, and the wrong one was declared fixed. The real one is
[chunk suppression follows the call, not a list of chunk types](suppression-follows-the-call-not-the-chunk-type.md).

Keep this decision: the setting is correct on its own terms. Do not keep its
claim about the crash.

# The symptom that this setting DOES address

An OpenAI-side rejection when history is rewritten between turns and the
provider item IDs no longer match what it stored.

# What it was not

The obvious theory was orphaned tool pairs, which `pair_tool_calls` exists to repair. That theory is wrong, and one line of evidence killed it: **`pair_tool_calls` logs at ERROR whenever it corrects anything, and it logged nothing** across the crashing runs. The history it saw was already well paired.

# The actual cause

We run the OpenAI **Responses API** with a reasoning model. pydantic-ai's `openai_send_reasoning_ids` **defaults to True for reasoning models**, and it does more than its name suggests -- its own docstring says it sends "the unique IDs of reasoning, text, and **function call** parts from the message history", and warns:

> This can result in errors ... if the message history you're sending does not match exactly what was received from the Responses API in a previous response, **for example if you're using a history processor. In that case, you'll want to disable this.**

Every agent here runs two history processors (`pair_tool_calls`, `elide_consumed_tool_results`). Our history is *by construction* not what the Responses API returned. So we echoed item IDs that OpenAI could not match, and it rejected the request.

That is why the symptom list looked so scattered. Branching, reverting, cancel-then-send and elision are all the same act: handing OpenAI a history it did not produce.

# The fix

`openai_send_reasoning_ids=False` in `build_model_settings` for OpenAI. Each request becomes self-contained -- content without provider item IDs -- which is what a rewritten history requires.

The trade-off is stated in the same docstring: most server-side tool items (web search, code interpreter, image generation) are replayed *by* ID and stop being sent back. We do not use those. Hosted tool-search items carry their state inline and still replay.

# Evidence it worked

The same multi-step shape that crashed twice now completes: 31 tool calls, 0 failures, no loop, 0 anomalies, FRAME to BUILD to VERIFY, real result (87 PF00069 kinases, intersected to 2 FIKK-family genes, mapped to *P. berghei* ortholog PBANKA_1225000).

# The general lesson

If you rewrite message history, you cannot also replay provider-side item IDs. Pick one. A framework default tuned for untouched histories is a landmine for any app with a history processor.

# Anchor

`build_model_settings` in `assistant-platform: packages/assistant-core/src/assistant_core/models/settings.py`. Guarded by `assistant-platform: packages/assistant-core/tests/unit/models/test_settings.py`; this application's own catalog is checked against the builder in `tests/unit/ai/models/test_settings.py`.
