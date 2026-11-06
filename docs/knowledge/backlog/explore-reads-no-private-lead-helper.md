---
type: Backlog
title: Explore reads no private Lead helper
description: The Explore node imports _LeadRunCapture and _answer_words, two private names of the Lead's turn modules; give them public names so the Lead's modules can change their private names without breaking Explore.
tags: [modes, explore, lead, refactor]
generated: { by: claude-code/opus-5.5, at: 2026-11-06T00:00:00Z }
status: proposed
---

# Explore reads no private Lead helper

## What is known

`ai/graph/explore_node.py` and `ai/graph/_explore_turn.py` reuse two private names from the
Lead's turn modules:

- `_LeadRunCapture` (`ai/graph/_lead_capture.py`): the run's record of its error, provider
  failure, model, effort and last input tokens, which `emit_lead_usage`,
  `noting_a_provider_failure` and `fallback_prose` take.
- `_answer_words` (`ai/graph/_lead_exchange.py`): the words of a card answer in an exchange.

A private name is a promise that only its own module reads it. Two agents now read these.

## What to do

Rename both to public names (for example `RunCapture` and `answer_words`) and update every
reader, the Lead's modules included. The Lead's output does not change. No alias of the old
names stays.

## Done when

No module outside `_lead_capture.py` and `_lead_exchange.py` imports a name that starts with
an underscore from them, and the unit suite passes.
