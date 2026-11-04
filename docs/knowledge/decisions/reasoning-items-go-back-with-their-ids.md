---
type: Decision
title: Reasoning items go back to OpenAI with their ids
description: Each call of a run sends the model's earlier reasoning items back with their ids and encrypted content. The setting that turned this off is gone, because live requests over every kind of rewritten history were accepted. Keeping the setting was rejected, because each call then started without the model's own reasoning.
tags: [agents, openai, message-history]
generated: { by: claude-code/opus-5.5, at: 2026-11-04T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-11-04T00:00:00Z }
status: stable
---

# What was decided

`build_model_settings` in `assistant-platform: packages/assistant-core/src/assistant_core/models/settings.py`
leaves `openai_send_reasoning_ids` at pydantic-ai's default, from assistant-core 0.3.0b16. A
request sends each earlier reasoning item with its id and encrypted content, followed by the
item it preceded. History processors keep or drop a response whole, so a reasoning item is not
split from its pair.

# The measurement

On gpt-5.6-luna through the Responses API, QA PlasmoDB, assistant-core 0.3.0b17, no request was
refused, and the captured requests hold the `rs_` ids and signatures:

| History | Result |
|---|---|
| A second turn on one thread | 666 genes, then 38 |
| A turn stopped by a kill, then another turn on the thread | Answered, 4 genes |
| `fork_conversation`, then a turn on the fork | 177 genes |
| `revert_conversation_to_message`, then a turn | 25 genes |

The library's log holds the earlier checks: after elision, after compaction, after a response
that holds only reasoning, and with items replayed a day later.

The debugger stores no user message, so the revert check added one row by hand to a throwaway
database. Its revert ran through the real function.

# What was rejected

**Keeping `openai_send_reasoning_ids=False`.** With it, pydantic-ai sends an earlier reasoning
item only as assistant text and never sends its encrypted content, so each call of a run started
without the model's reasoning. The earlier reason for the setting was a claim that OpenAI refuses
an id on a rewritten history. The crash that claim explained came from the browser client, as
[chunk suppression follows the call](suppression-follows-the-call-not-the-chunk-type.md) records.

# Anchor

If OpenAI refuses an item id on a history not listed above, the setting comes back only with the
request that shows it.
