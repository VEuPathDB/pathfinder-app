---
type: Decision
title: A picked reading stands in for the words it reads
description: A question about a free-text or range parameter offers two or three readings the site validates, each an option that binds its value under the count the site returned for it, and names by number the requirements they approximate. A reading the researcher picks, or one FRAME binds from their answer in words to a question that offered it, is recorded on the criterion as its accepted reading, replaces those requirements by key with a stand-in, holds only while the criterion binds its values, and is judged by VERIFY as met by the parameter, its caveat a caveat and never an unmet row; when it ends, its stand-in is withdrawn. Judging the original words, matching requirements by the criterion's text and letting FRAME declare a reading on its own were rejected.
tags: [agents, lead, frame, verification, parameters]
generated: { by: claude-code/opus-5.5, at: 2026-10-21T00:00:00Z }
status: stable
---

# What was decided

A question that asks for a raw threshold or a raw expression hands the
researcher the site's grammar. A question about a free-text or range
parameter instead offers `readings` (`SlotQuestion.readings`, at most three,
never one, never beside `options`): each a label in the researcher's terms
with its numbers, the value it binds, and a caveat that states what it leaves
out. FRAME takes them from the recipes the parameter's help states, and a
request one recipe states exactly is bound with no question.

**A reading is an option that binds, on a value the site builds.**
`SlotQuestion.typed` makes one `ReadValues` option per reading, carrying the
keys of the requirements the question names by number. The keys belong to the
question, since every reading of it replaces the same requirements; keys
written on each reading are read as the question's. A FRAME output
validator (`ai/agents/frame_reading_checks.py`) sends back a reading on a
parameter that is no free-text or range parameter, a reading whose criterion holds another open parameter,
a question that names no key while the pinned list holds some,
a requirement number the pinned list lacks, and a value the site's validation
refuses, with the site's words, and two readings the site spells alike; a
value it accepts reaches the card in the site's spelling. A key the list lacks
is refused only while the list holds keys. Past [the refusal bound](an-output-check-refuses-at-most-twice-and-never-on-the-last-answer.md), a reading the site
refuses is left off the card with the site's reason in the summary; a question
left with fewer than two readings reaches the card with its text and options
alone. Readings that name no stated requirement reach the card, and a pick of one
carries `names_no_requirement`, which its caveat and VERIFY's line state. A check the site
does not answer within the budget a count read has leaves the reading as
written, as an unanswered count does. After the pass, `ai/lead/readings.py` counts each reading
under the turn's `TurnCounts` and records it as a `reading` measurement, so
the card label carries the count; a count that does not arrive leaves the
label without one. A card pick runs the same validation, and a pick the site
refuses binds nothing and is reported to the Lead.

**An accepted reading stands in for the words.** Two paths record
`Criterion.accepted_reading`: a picked `ReadValues` option, bound as the
card's value with no model in between, and `set_criterion(reading=...)` when
the researcher answered in words. `ThreadRequirements.follow_readings`
compares the spec before and after each FRAME pass, each card answer and
each replay of a change written on the site. A
reading newly held is accepted: it is recorded as a requirement of the
researcher's, on the question's dimension (an organism or record-type scope
becomes `other`), and the live requirements whose keys the reading carries
are replaced by it, whatever words FRAME chose for the criterion. A reading
that ended withdraws its stand-in.

**A reading holds while its values hold.** `Criterion.held_reading` returns
the reading only while the criterion binds every value the reading binds.
The caveat, the ledger line, the check and `follow_readings` read it, so a
restatement, a search changed on the site or a re-bind at other values ends
the reading on every path. A re-bind at the same values keeps it.

**Only an offered reading is accepted.** `set_criterion` refuses a reading
when no question open now, or answered by the message this turn reads,
offered readings on that criterion; when the label is not one it offered; and
when the bound values are not the ones that reading binds.

**VERIFY judges the reading.** The check's request block lists each held
reading with the values that state it: its row is met by that step, `how`
`parameter`. A reading with a caveat adds a `reading` caveat to the facts and
the ledger, and the Lead states it in the researcher's terms.

# What was rejected

- **Judging the original words.** An approximation never meets the words it
  approximates, so every reading the researcher chose would fail the check.
- **FRAME declaring a reading on its own.** A reading nobody offered would
  stand in for words the researcher never saw replaced.
- **Matching the requirement by the criterion's text.** FRAME words the
  criterion in its own terms, so a paraphrase would leave the original words
  live beside the reading; the question names the requirements by number.
