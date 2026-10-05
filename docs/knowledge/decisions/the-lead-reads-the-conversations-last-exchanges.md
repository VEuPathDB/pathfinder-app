---
type: Decision
title: The Lead reads the conversation's last exchanges
description: Every Lead run reads the conversation's last six exchanges, each the researcher's message or card answer and the reply as the researcher read it, from a pinned section of its instructions. Replaying earlier turns as model message history and rebuilding exchanges from the event log were rejected.
tags: [agents, lead, context, conversation]
generated: { by: claude-code/opus-5, at: 2026-10-04T00:00:00Z }
status: stable
---

# What was decided

The Lead starts every run from the new message and its pinned sections; it is
never handed the earlier turns as messages. `StrategyDomainState.exchanges` keeps
the conversation's last `EXCHANGE_WINDOW` (six) exchanges
(`domain/exchanges.py`): what the researcher wrote, or how they answered a card,
the reply exactly as it was rendered to them, and the question or offer a card
turn ended on. `ai/graph/_lead_exchange.turn_exchange` builds one at the end of
each Lead run, from the same `render_reply` text the stream carried, and
`lead_pins.pinned_conversation` renders them as "The conversation so far" before
"User's latest message". A number in an exchange held when it was shown; the
ledger and the facts hold the strategy now.

# Why

A follow-up that points at what a reply said ("the third gene you listed", "use
the experiment you recommended", "that same sample again") had nothing to point
at: the Lead's briefing held what the strategy is, never what the researcher was
shown. Measured on plasmodb before the window: asked for the third gene of a
listed sample, the Lead re-read the step and named a different gene in 2 of 3
runs; asked to use the experiment it had recommended, it built on another
experiment in 3 of 3 runs.

# What was rejected

- **Earlier turns as model message history, the runtime's thread history.**
  `assistant_core.graph.thread_history`, which the one-agent graph `site_help`
  runs on replays, carries every model message of every turn: each tool call and
  result, unbounded, and each answer as its raw references. A Lead turn holds
  tens of sub-agent calls and their deltas, so the replay grows without bound and
  brings each turn's stale counts back into every request; the Lead's run also
  already uses `message_history` to resume a parked approval card inside a turn.
- **Rebuilding exchanges from the event log at turn start.** The log holds the
  assistant's chunks but not the researcher's messages, and reducing chunks to
  messages is the browser client's job; a second reducer in Python would drift
  from it.
- **A summary of older turns.** The ledger and the requirements list already
  carry what outlasts six exchanges.
