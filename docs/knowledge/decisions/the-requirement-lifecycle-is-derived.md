---
type: Decision
title: The requirement lifecycle is derived
description: The classifier states requirements by dimension and value, and the ones a message takes back; the thread derives every replacement, withdrawal and successor from those statements and from what it holds. FRAME's disposition of a criterion is read from its wire values, and a review row's status agrees with its answer by construction. Model-declared replacement keys checked by a gate were rejected.
tags: [agents, lead, frame, verification, requirements]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: stable
---

# What was decided

`UserIntent` states requirements and nothing about their identity:
`explicitConstraints` (dimension, value, label, hard) and `withdrawn`, the
requirements the message takes back, typed the same way. It names no key and no
successor. `ThreadRequirements.record(intent, messages)`
(`ai/graph/thread_requirements.py`) derives the lifecycle:

- A stated value of a dimension that holds one value (organism, record type,
  threshold, fold change, percentile, data type, comparator) replaces the value
  the thread held for it, which retires as `replaced(by=<new key>)`
  (`stated_requirements.with_requirements`). Two values stated in one message
  both stand, and a message that adds an alternative with an include verb
  (`message_reading.adds_an_alternative`) adds the value beside the held one.
  `other` and `combination` hold many values; a new combination displaces a held
  one over the same terms, and a message that swaps an `other` value lists the old
  one in `withdrawn`.
- A value only the classifier composed (`assumed`) never displaces a value the
  researcher stated of a single-valued dimension: it is dropped, neither recorded
  nor retired (`stated_requirements._outranked`). A stated value displaces an
  assumed one.
- `other` holds many values everywhere, the ledger's merge included: two `other`
  values collapse only when their non-filler words are equal
  (`constraints.content_words`, `constraints.merge_constraints`), the stated one
  winning.
- A `withdrawn` statement retires each held requirement of its dimension whose
  value and the statement's carry each other's words, filler words aside
  (`constraints.states_the_content`), or the one value a
  single-valued dimension holds (`requirement_lifecycle.withdrawn_by`). It retires
  as `replaced` by a value of the same dimension the message states, else as
  `withdrawn` on this message. A statement that names nothing held retires
  nothing.
- A value only an ask of the message carries is no requirement, and a
  `follow_up_question` is all ask (`UserIntent.researcher_asks`); a compared side
  of a `follow_up_question` is never one (the `UserIntent` validator), and a
  card sentence is never recorded as the researcher's words.
- An approved `delete_step` retires each live requirement only the deleted
  criteria's text stated, filler words aside
  (`retire_what_a_delete_leaves_unanswered`).
- A review row is dropped as a question only when its words are, in order, the
  words of an ask, of one sentence of an ask, or of a sentence a message ends with
  a question mark (`question_rows.without_questions`). An ask erases no row that
  only shares its words.

FRAME's disposition of each criterion the dispatch found is the computed diff of
the two specs (`frame_dispatch.derived_changes`): `kept` only when no wire value
moved. `FrameResult.changes` is omitted from FRAME's schema, so the pass writes no
account.

`RequirementCheck` refuses `unmet` with a non-empty `answered_by`. A `met` row a
text query alone answers is shown `unshown` when a sampled record shows it
missing and `unjudged` when no record judged it (`shown_status`); the gap of an
unjudged row reads "no sampled record judged it" and holds no check short of
success.

# What was rejected

**Model-declared replacement keys with a gate that checks them.** The classifier
wrote `withdrawnRequirements` as `<dimension>:<value>` keys with a `replacedBy`
successor, and the classification gate refused a key the thread did not hold and
a successor it already held. The key is the canonical value the thread recorded,
so the gate refused the correct withdrawal whenever an upstream validator had
dropped or rewritten the constraint the key named, and the successor duplicated
what the message's own constraint already stated.

**A disposition the pass declares, refused when it disagrees with the values.**
The refusal read the pass's label, so a pass that moved exactly what the request
asked was refused for a wrong word. The values are the account.

**An `unmet` row that names the step answering it.** A combine joined another
way and a text row a record shows missing were both filed as `unmet` with steps
named, so a reader could not tell a requirement nothing answers from one the
records leave short. The note names the combine, and the records' verdict is a
status of its own.
