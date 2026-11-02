---
type: Decision
title: A criterion links the requirement it answers
description: FRAME writes on each criterion it binds the numbers of the held requirements the criterion answers, with the parameter that carries each value, and the tool maps each number to the requirement's id. A delete, the organism fold, the withdraw offer on a question and the gap rows read those links and do nothing without one. Word overlap between a criterion's text and a requirement's value, a link the model writes with no validation, and links held on the requirement instead of the criterion were rejected.
tags: [agents, frame, lead, requirements, verification]
generated: { by: claude-code/opus-5.5, at: 2026-11-02T00:00:00Z }
status: stable
---

# What was decided

`Criterion.answers` (`domain/strategy/operational_spec.py`) is a list of
`RequirementLink`: `requirement`, the id the thread minted for a held requirement,
and `param`, the parameter of the criterion's search that carries the requirement's
value, or null.

FRAME writes the links on the `set_criterion` call that binds
(`ai/tools/standalone/_frame_answers.py`), by the numbers of "Requirements the
researcher stated" (`requirement_reports.numbered_requirements`). The tool maps each
number to the requirement's id. A number the list lacks, and a parameter the
search's sheet lacks, go back to FRAME as a retry that names the valid ones. An
empty list says the criterion answers no held requirement; a call that names no
`answers` keeps the links the criterion holds. The links survive every rewrite
that keeps the criterion's identity: a rebind, a card pick, a reading, a fold, the
waiting EDA criterion and its export, and the step words a hydrated spec reads.

Four paths read the links:

- **A delete** (`ThreadRequirements.retire_what_a_delete_leaves_unanswered`)
  withdraws each live requirement that a deleted criterion links and no remaining
  criterion links. An organism or a record type is never withdrawn.
- **The organism fold** (`spec_fold.FoldedStructure.holding_open`) holds open the
  requirements the dropped criterion links, less an organism, a record type and a
  combination, which the carrier's step meets. Each one is a gap while no
  criterion of the spec links it (`OperationalSpec.unexpressed`).
- **The withdraw offer** (`questions.with_withdrawals`) gives the drop and keep
  options to an optionless question whose `criterion_id` names a criterion that
  links the requirement; otherwise the card asks a question of its own.
- **The gap rows** (`caveats.check_gaps`) carry the requirement's id. A row whose
  requirement is withdrawn or replaced is no gap.

With no link, each path does nothing: a delete withdraws nothing, a drop holds
nothing open, a question gains no option.

A card question of the Lead's that asks for a stand-in names the numbers of the
requirements it replaces (`CardQuestion.replaces`). The ledger prints each held
requirement under its number. The numbers are checked and mapped to ids when the
card is shown (`lead_consult.consult_can_ask`), so a requirement the answer's turn
adds does not move them, and the answer replaces exactly those requirements.

# Why

Each of these paths compared the words of FRAME's criterion text, a question's
prompt or a gap's text with the words of a requirement's value. Both strings are
model-written, so a plural, a paraphrase or a Pfam name decided whether a delete
retired a requirement, whether a drop held one open and whether a question was
about one. The criterion is where FRAME decides what answers what, so the link is
written where that decision is made, and checked against the list FRAME read.

# What was rejected

**Word overlap between the texts.** It reads two strings a model wrote; see
[the requirement lifecycle is derived](the-requirement-lifecycle-is-derived.md) and
[a withdrawal names a held requirement by its number](a-withdrawal-names-a-held-requirement-by-its-number.md)
for the misses it measured.

**A link the model writes with no validation.** A number or a parameter that does
not exist would link nothing, and every path would abstain without saying why.
The retry names the valid values inside FRAME's own run.

**Links held on the requirement instead of the criterion.** A requirement is the
researcher's and outlives every criterion; a criterion is rewritten, renumbered and
dropped by each pass. Links on the requirement go stale whenever a pass moves a
criterion, and a delete or a fold would have to find and edit them.

# Anchors

`domain/strategy/operational_spec.py`, `ai/tools/standalone/_frame_answers.py`,
`ai/graph/thread_requirements.py`, `domain/strategy/spec_fold.py`,
`domain/strategy/questions.py`, `domain/caveats.py`, `ai/lead/lead_consult.py`,
`tests/unit/ai/tools/test_a_criterion_links_the_requirement_it_answers.py`,
`tests/unit/ai/lead/test_a_chosen_stand_in_retires_what_it_replaces.py`.
