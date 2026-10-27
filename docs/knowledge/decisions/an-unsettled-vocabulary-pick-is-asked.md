---
type: Decision
title: An unsettled vocabulary pick is asked
description: With the OpenAI Decisions service on, a narrowed vocabulary read carries the entry a Decisions choice picks and how sure it is; a FRAME binding of a value FRAME chose on a parameter whose pick is not settled becomes a slot question to the researcher with the pick, the kept entries and a free-text route. Refusing the binding until FRAME asks, binding the pick silently, and a word rule over the entry labels were rejected.
tags: [frame, consult, vocabulary, decisions]
generated: { by: claude-code/opus-5.5, at: 2026-10-27T00:00:00Z }
status: stable
---

# What was decided

veupathdb-mcp 0.2.0b54 can ask the OpenAI Decisions API during a narrowed vocabulary
read (`DECISIONS_ENABLED`). The read then carries `ParameterInfo.vocab_pick`: the entry a
choice over the kept entries picks (or none fits), the choice's confidence, the
probability a fit predicate gives that the entry states the requirement, and `settled`,
true when the lower of the two reaches `DECISIONS_VOCAB_MIN_CONFIDENCE`.

- `get_parameter_options` takes `requirement`, the number of a requirement the
  researcher stated. With the service on, that requirement's words lead the read's
  `request`, so the fit predicate judges the researcher's requirement and not FRAME's
  query. A number the list does not hold is refused with the numbers it does hold.
- The read records the pick (`AgentToolState.vocab_picks`, a `PickRead` from
  `domain/strategy/vocab_picks.py`) and adds a note to the result: a settled pick is the
  entry to bind unless the request names another; an unsettled one, or none, says the
  binding is asked.
- `hold_an_unsettled_pick_to_a_question`, FRAME's last output validator, turns every
  criterion whose value of that parameter FRAME chose (`source == "chosen"`) under an
  unsettled pick into a `SlotQuestion` on that slot and ends the pass `needs_user`. The
  question names the pick and its confidence, offers the pick, the bound value and the
  kept entries by their site labels, recommends the pick, and the card's note is the
  free-text route. A value the researcher stated or answered on a card is never asked.
- `search_for_searches` shows each result's `decisionProbability` when the choice gave
  one.

With the service off the read carries no pick, the request is the phrasings the
messages state, and no question is added.

# Why

The live kinase runs bound a different InterPro entry each time from the same lookup,
and the word rules over entry labels (`_frame_lookups.py`) cannot tell a broader entry
from the one the requirement names. A typed confidence from a model asked only that
question is a measured signal, and a question to the researcher is the one route that
cannot bind a wrong entry silently.

# Rejected

- **Refusing the binding until FRAME writes the question.** It is one more model retry
  that may be answered with another wording; the question is built from typed state,
  so PathFinder writes it.
- **Binding the pick silently.** An unsettled pick is a recorded doubt, and a strategy
  built on it reports a count for a requirement the researcher may not mean.
- **A word rule over the labels to decide which entry the request means.** It is the
  kind of special case the rule audit found refusing correct work.

# What would prove this wrong

`tests/unit/ai/agents/test_an_unsettled_vocabulary_pick_is_asked.py` replays the
recorded PlasmoDB InterPro read and the two recorded Decisions exchanges ("protein
kinase": IPR011009 at choice 0.89, fit 0.31, not settled) and holds the question, the
note, a stated value left alone, a settled pick never asked, and the off path sending
nothing.
