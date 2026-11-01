---
type: Decision
title: A requirement is the researcher's when it quotes their words
description: A requirement is stated, and so the researcher's, when the classifier gives a verbatim quote that is an exact casefolded substring of a researcher message; without one it is assumed. This records provenance, not meaning. A combination is stated when every member is stated and the researcher's text between the members' quotes states its operator, read by the connective rules that already exist. The word-containment test on model-written values was measured on 1,018 recorded classifications and called 60 distinct stated requirements assumed; it is rejected, as are the value itself as the quote and a model that judges meaning.
tags: [agents, lead, requirements, provenance]
generated: { by: claude-code/opus-5.5, at: 2026-11-01T00:00:00Z }
status: stable
---

# What was decided

**Provenance by quote.** Each requirement the classifier writes carries `quote`,
a span the researcher wrote. The requirement is `stated` when the quote is an
exact, casefolded substring of one of the researcher's messages on the thread
(the message being classified, the original request, or words the researcher
wrote on a card); otherwise it is `assumed`. An assumed requirement is surfaced
and gates nothing, as today. The quote says where the words came from; it says
nothing about whether the typed value means what the quote means. That stays
the classifier's job, and the verdict checks the typed value
([a verification verdict is computed from the site](a-verification-verdict-is-computed-from-the-site.md)).

**The combination's operator stays the researcher's.** A combination is stated
when every member is stated and the researcher's text between two consecutive
members' quotes, located by substring index in message order, states the
operator. The connective rules of
[the strategy answers to a spec](the-strategy-answers-to-a-spec.md) read that
text unchanged: they read researcher text, not model text. What goes is the way
a term is found: `message_reading._span` locates a model-written term by its
words, the phrase else the shortest window holding every word. A quote is
located by its index. An include-verb OR arm is checked the same way.

The code keeps the word test (`message_reading.message_states_constraint`,
`stated_requirements.attributed`) until step 6 of
[backlog item 77](../backlog/requirements-are-typed-data.md) lands.

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

**Dropping the connective reading for a model-declared operator.** The operator
is what the researcher wrote between the terms; a model-declared operator is the
model's word for it, which is what this decision removes.

# What would prove this wrong

A replay of the same saved runs under the quote schema in which a requirement
the researcher stated has no verbatim quote the classifier can give, or a quote
that is a substring of a researcher message attributes a requirement the
researcher did not state. The unit tests step 6 adds hold that a quote no
researcher message holds never makes a requirement stated, and that a
combination's operator is read from the text between its members' quotes.
