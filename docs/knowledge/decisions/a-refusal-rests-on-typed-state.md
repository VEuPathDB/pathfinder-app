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

On 2026-10-31 every remaining check that refused or withheld a model's output by reading its
text with a pattern was removed too, with its tests and plumbing:

- the note check on the Lead's reply and a card's reply (`note_facts`, its own refusal bound
  `TurnMarkers.prose_refusals`, `TurnFacts.request_messages` and `holds_site_data`), the
  auditor reply's copy of it (`HoldTheReply`) and the audit synthesis's number and link check;
- the code-fence half of the off-topic reply rule; a long off-topic reply is still refused by
  its length;
- VERIFY's control-count, control-id and sampled-gene claims read from its prose
  (`evidence_claims.py`); the typed review (sampled genes no read returned, sources no read
  returned) is still held to the turn's reads;
- the classifier's operator check against the message's connective words
  (`unstated_operator_refusal`);
- FRAME's stated-combination and stated-OR structure refusals (`first_combination_violation`,
  `unstated_union`), which matched requirement words to criterion text;
- the proposal card's coverage check (`card_coverage.py`, `refuse_a_card_that_leaves_a_part`)
  and the `answers` and `leftToAsk` keys only it read;
- the two pick refusals that compared label words with the lookup term and the request
  (`_refuse_a_pick_beside_the_exact_term`, `_refuse_a_pick_off_the_request_words`);
- the rationale check that read a kept reason's words for an old organism value;
- the criterion-text half of the edit guard's stated values (`states_the_wire_form` over the
  criterion's text); a value is stated when a requirement the researcher stated grounds onto
  it;
- the EDA export's caption check (`caption_verdict`) and the `caption` argument it read.

Kept, because each compares typed values or the site's answer: the refused-call memory (the
tool name and a digest of the typed arguments, on the Lead's toolset and every sub-agent's),
schema validation, the lookup membership check (a pick must be an entry a lookup matched), the
obsolete-label refusal (the site's label and the researcher's message), the grounding of a
stated requirement against the spec, and the compaction's identifier check, which a recorded
measurement backs ([a compaction keeps every identifier](a-compaction-keeps-every-identifier.md)).

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
- **Widening the guards that refused too much** (backlog 63). A wider word pattern is still a
  word pattern, and it fails on the next phrasing.
- **Refusing a reply whose words claim an approval** (backlog 61). The fault was missing data:
  the Lead could not see who chose a reading. Each reading now says who chose it
  ([a reading says who chose it](a-reading-says-who-chose-it.md)).

# What would prove this wrong

A recorded run where a removed rule's fault reaches the researcher as a wrong answer that
no typed rule catches.
