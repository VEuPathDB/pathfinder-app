---
type: Backlog
title: The Auto router's floor is measured on the production context
description: The 0.65 build floor was measured on context text built by hand from recorded runs and on only 10 explore messages; measure it again on the context the route node sends, with 20 to 30 explore messages written by testers and the help, remember and off-topic messages.
tags: [modes, router, decisions, measurement]
generated: { by: claude-code/opus-5.5, at: 2026-11-06T00:00:00Z }
status: proposed
---

# The Auto router's floor is measured on the production context

## What is known

`BUILD_PROBABILITY_FLOOR` (`domain/modes.py`) is 0.65. It was measured on 178 messages (168
build, 10 explore): 93.3 percent, with 19 of 168 build messages sent to Explore and 9 of 10
explore messages caught. See
[the decision](../decisions/a-thread-answers-in-explore-or-build.md).

## Why the number may not hold

- **The context differs.** The measured conversation and strategy text was built by hand from
  recorded runs. The route node sends `exchanges_text` over the thread's exchanges and
  `strategy_line` (`ai/graph/turn_route.py::route_request_for`). The two differ on a card
  answer (the answer's words against a bare "answered the card"), on a task result, on how a
  reply is rendered and on the strategy line ("Strategy: 1 step; the final step ... returns 70
  genes" against "Strategy: - pushed: N").
- **The explore class is small.** 10 messages give one miss a weight of 10 points.
- **Three kinds of message were left out.** A help question, a request to remember and an
  off-topic message all route through Auto, and none was measured.

## What to do

1. Collect 20 to 30 explore messages that testers wrote, plus help, remember and off-topic
   messages, each labelled with the mode that should answer it.
2. Render each item's context with `route_request_for` from its recorded thread, so the
   request is the one production sends.
3. Run the set three times on gpt-6-luna and report accuracy per class, the build messages
   sent to Explore and the explore messages sent to Build at floors from 0.5 to 0.8.
4. Set `BUILD_PROBABILITY_FLOOR` from that table and update the decision.

## Done when

The decision's figures come from the production context, and the floor in `domain/modes.py`
is the one that table supports.
