---
type: Decision
title: A reading says who chose it
description: Every reading a criterion holds and every reading a framing pass built without asking carries who chose it, the researcher on a recorded card or the assistant, and the ledger the Lead and each sub-agent read states it; refusing a reply whose words claim an approval was rejected.
tags: [lead, ledger, readings, provenance]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: stable
---

# What was decided

`domain/strategy/readings.py::ReadingChooser` names who chose a reading:
`researcher_on_a_card` or `assistant`. `AcceptedReading.chosen_by` holds it. A pick on a
question card records `researcher_on_a_card` (`ai/lead/lead_consult.py`); a reading a
framing pass binds from the researcher's typed answer records `assistant`, because the
pass read the words, and it keeps a card pick of the same reading as the card's
(`ai/tools/standalone/_frame_reading.py`). A stored reading with no chooser is the
assistant's: no recorded card holds it.

A reading a framing pass built without asking (`FrameResult.chosen_reading`, kept as
`StrategyDomainState.named_readings`) is the assistant's until the researcher picks one
of its labels on a card, which `StrategyDomainState.picked_readings` records.

The ledger summary, which the Lead reads on every request and each sub-agent receives,
lists every reading under `## Readings` with its chooser
(`domain/strategy/reading_choices.py::reading_choice_lines`), and the full frame section
names it on each criterion's `READING` line. Each bound value line names who set it in
words ("stated by the researcher", "picked by the researcher on a card", "chosen by you",
"the site's default", "held by the strategy as it stood").

# Why

A reply once said "the reading you approved" when the researcher had picked nothing and a
framing pass chose the reading. The ledger listed no chooser, and its line for a held
reading said "the researcher accepted" whatever had chosen it. With the chooser in the
data the Lead reads, a true reply has the fact it needs.

# What was rejected

- **Refusing a reply whose words claim an approval.** It reads the model's text with a
  pattern, misses the next phrasing and refuses a true sentence that quotes one (see
  [a refusal rests on typed state](a-refusal-rests-on-typed-state.md)).

# What would prove this wrong

A recorded turn whose ledger states the assistant chose a reading and whose reply still
says the researcher approved it.
`tests/unit/domain/strategy/test_a_reading_says_who_chose_it.py` and
`tests/unit/ai/lead/test_the_ledger_says_who_chose_each_reading.py` hold the data and the
rendering.
