---
type: Decision
title: A requirement is the researcher's when it quotes their words
description: A requirement is stated, and so the researcher's, when it carries a verbatim quote that is an exact casefolded substring of a researcher message; without one it is assumed. This records provenance, not meaning. No connective is read: a combination is the researcher's only by its own quote, and its operator is FRAME's tree. The word-containment test on model-written values was measured on 1,018 recorded classifications and called 60 distinct stated requirements assumed; it is rejected, as are the value itself as the quote and a model that judges meaning.
tags: [agents, lead, requirements, provenance]
generated: { by: claude-code/opus-5.5, at: 2026-11-01T00:00:00Z }
status: stable
---

# What was decided

**Provenance by quote.** Each requirement the message reader writes carries `quote`,
a span the researcher wrote. The requirement is `stated` when the quote is an
exact, casefolded substring of one of the researcher's messages on the thread
(the message being classified, the original request, or words the researcher
wrote on a card); otherwise it is `assumed`. An assumed requirement is surfaced
and gates nothing, as today. The quote says where the words came from; it says
nothing about whether the typed value means what the quote means. That stays
the reader's job, and the verdict checks the typed value
([a verification verdict is computed from the site](a-verification-verdict-is-computed-from-the-site.md)).

**No connective is read.** A combination is stated only when its own quote is
a substring of a researcher message, like any other requirement. Neither the
message reader nor a card answer writes one, so one comes only from a thread
recorded before them. How requirements combine is FRAME's tree, read against the
researcher's words
([operators come from FRAME's tree](operators-come-from-frames-tree.md)).
The include-verb OR arm, the word location of a term (`message_reading._span`)
and the connective rules (`read_combination`) are deleted.

**What is built.** `stated_requirements.attributed` applies the quote rule and
nothing else: no word of the value is matched against a message, and a value
the thread already holds is not made stated by being written again. A
requirement no message reading wrote carries the source the code gave it: a
card answer and an accepted reading are recorded as the researcher's when the
card records them (`ThreadRequirements.record_requirements`), and a held one
keeps its id and source when a reading restates it. A requirement is recorded
when the reading writes it; no test of its words against the message's asks,
its compared sides or a picked card label drops it. A pick binds its option by
id. A bound text is `chosen` when the quotes of the requirements its criterion
links to that parameter all write other words
([a text cut from a stated phrase is chosen](a-text-cut-from-a-stated-phrase-is-chosen.md)).

# The measurement

An offline replay ran the current `attributed` over every saved debugger and eval
run with a completed classification: 522 conversations, 1,018 classifications,
1,920 requirements, no model and no site call. Each decision was read against the
message.

- Of 1,794 requirements of a kind other than a combination, 142 were marked
  assumed (99 distinct). 88 of them (60 distinct) the researcher had stated in
  other words: "has an ortholog in Toxoplasma gondii" for "have an ortholog in
  Toxoplasma gondii", "exclude genes with 2 to 99 transmembrane domains" for
  "excluding any gene with 2 to 99 transmembrane domains", "Leishmania genomes"
  for "every single Leishmania genome", "gene length greater than 10 kb" for
  "genes longer than 10 kb". 28 more were doubtful. An assumed requirement is
  not hard, so none of the 60 was checked as the researcher's.
- No requirement was marked stated that the researcher had not written.
- 1,612 of the 1,920 values (84.0%; 573 of 778 distinct) are themselves a
  casefolded substring of a researcher message. 131 values marked stated today
  (60 distinct) are not: the classifier paraphrased words the researcher wrote.
  Each of the 60 wrongly assumed requirements has a verbatim span in its
  message that states it.
- Of 120 combination attributions (60 distinct), 10 were wrong. Six were stated
  combinations marked assumed because a term's words were not all in the
  message ("in", "NOT", "predicted"), two values with mixed operators did not
  parse, and two comparisons ("more highly expressed in the bloodstream form
  than in the procyclic form", "compare the wild type samples with the DHC
  mutant samples") were read as a stated AND, because a connective that holds
  no conjunction takes AND. 14 were doubtful.
- The include-verb OR arm (`stated_requirements._added_as_an_alternative`) never
  decided an attribution.

# What was rejected

**Containment of the value's words in a message** (`message_states`). It reads a
model-written value, so a plural, a verb form or a filler word decides
provenance. The measurement above is the evidence.

**The value as the quote.** 84% of values are verbatim, but 131 stated
requirements are paraphrases a substring test would demote, and none of the 88
wrong ones is a substring. The quote has to be a field of its own.

**A model that judges whether the researcher meant the requirement.** Meaning is
the classifier's job already; a second model per requirement adds a call, a
probabilistic answer and a no-answer branch, and provenance is a fact a
substring test settles exactly.

**A model-declared operator.** A combination requirement whose operator the
model writes is the model's word for what the researcher wrote between the
terms. The operator comes from FRAME's tree and is checked against the
researcher's words, never recorded from a model's value.

# What would prove this wrong

A replay of the same saved runs under the quote schema in which a requirement
the researcher stated has no verbatim quote the reader can give, or a quote
that is a substring of a researcher message attributes a requirement the
researcher did not state. The unit tests hold that a quote no researcher
message holds never makes a requirement stated, and that a value whose words a
message carries without a quote is assumed
(`tests/unit/domain/strategy/test_a_quoted_requirement_is_the_researchers.py`).
