---
type: Decision
title: A refusal rests on typed state or the site's answer, never on a phrasing
description: The harness refuses a call or a reply only for what typed state, the catalog or the site holds; the rules that matched words, counted characters, demanded one question shape or replayed past cases were removed. Keeping each rule that once fixed one live run was rejected.
tags: [frame, lead, contract, refusals]
generated: { by: claude-code/opus-5.5, at: 2026-10-27T00:00:00Z }
status: stable
---

# What was decided

A refusal reads typed state (the spec, the turn's markers, the facts beside the reply,
the requirement list), the catalog or the site's own answer. These were removed:

- `set_criterion`'s rationale term checks (the term held to words of the search's name or
  description, a value it sends, a null parameter, the only match, a record type that
  decides something) and the 160-character limit on the reason. The `why` stays a schema
  field; a term that names a parameter by its wire name is shown by its display name.
- The qualifier check (`_frame_qualifiers.py`): a word of the criterion held to the
  parameters of the searches the pass read.
- The fixed menu of the Lead's own card questions (`refuse_a_card_that_binds_nothing`): an
  option that binds no recorded value comes back as the researcher's words.
- FRAME's question cascade: the free question over a draft with no open slot, the demand
  for readings on a value asked in words, the every-genome presence question and the
  comparison-reading check. A question on a slot the draft lacks is still sent back.
- The added-criterion check on an edit (`added_criteria.py`).
- The reply rules `claimed_frame`, `blamed_the_site`, `unmade_change`, `unbacked_absence`,
  `unrecorded_question`, `unfinished_work` and `unstated_reading`, and the prose faults
  `number_word`, `zero_word`, `values_without_noun`, `tally_of_a_step`, `unnamed_dispute`
  and `group_certainty`.
- FRAME's step 0 case replay (`search_memory(kind="case")` before binding). The typed case
  write after a passing check stays, and the Lead still recalls a case on purpose.
- Case-keyed prompt text: the OrthoMCL block moves to a section only an OrthoMCL pass reads
  (`ai/agents/site_notes.py`), and example strains, phrasings and searches leave the
  all-site prompts.

# Why

The audit of 374 recorded turns found every caught error came from typed or site-grounded
rules (search names, parameters, record types, unheld references, tally columns), while
each rule above refused more correct work than wrong: the term checks refused the only
group-to-protein transform, the number-word rule refused 11 of 13 correct drafts, the
added-criterion check blocked the transform a count needed every time it fired, and 13 of
21 reply rules never fired. A refusal that reads words moves the failure to the next
phrasing; a refusal that reads typed state holds whatever the phrasing.

# Rejected

- **Keeping each rule because it fixed the run it was added for.** One run is one sample,
  and the rules contradicted each other (one demanded a question the next refused).
- **Narrowing each rule with more word lists.** It is the same mechanism with a larger
  surface.

# What would prove this wrong

A recorded run where a removed rule's fault reaches the researcher as a wrong answer that
no typed rule catches.
