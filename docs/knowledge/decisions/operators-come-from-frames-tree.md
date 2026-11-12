---
type: Decision
title: Operators come from FRAME's tree, read against the researcher's words
description: How requirements combine is the tree FRAME builds; after each framing pass one Decisions question per combine reads the researcher's messages and the two branches' quotes, a confident other operator is asked on the card, and a combine shows who chose its operator. A model-written combination requirement, reading connective words and asking on every combine were rejected.
tags: [frame, lead, consult, decisions, requirements, structure]
generated: { by: claude-code/opus-5.5, at: 2026-11-03T00:00:00Z }
status: stable
---

# What was decided

No requirement states how other requirements combine. The message reading writes
no combination, a card answer is recorded on its question's dimension and never as
a combination, and no code reads a connective. The operators are the tree FRAME
builds (`OperationalSpec.structure`).

After each framing pass that lands a structure, `ai/lead/operator_reader.py::read_the_operators`
runs over the draft, never inside FRAME's own tool loop (`ai/lead/frame_dispatch.py::run_frame`):

- Same-operator INTERSECT and UNION chains collapse into one combine first
  (`domain/strategy/operator_reading.py::chains`).
- A combine is read only when each of its inputs holds a criterion that links
  (`Criterion.answers`) a stated requirement with a quote, other than an organism
  or a record type and other than a requirement more than one input links. An
  assumed branch, such as an implied definition, costs no call and its combine
  shows as the assistant's.
- One Decisions question per combine (`veupathdb_mcp.catalog.decide`, metered with
  the turn) reads the researcher's messages and each branch's quotes, nothing
  else. The choices are intersect, union, left minus right, right minus left,
  colocated, not combined directly and not stated; a combine of more than two
  inputs is asked intersect, union, not combined directly or not stated.
- The newest message is read first, alone (`operator_reader._newest_first`). When
  it states an operator at or above the floor, that reading stands and the history
  is not read; otherwise the question is asked again over every message, oldest
  first. A message that changes a combine therefore overrides the words that built
  it, and the order is enforced by code, not by asking the model which message won.
- The answer is typed on the spec as an `OperatorReading` keyed by the combine's
  criteria and the operator FRAME built: `agrees`, `disagrees` (an other operator
  at or above `DECISIONS_VOCAB_MIN_CONFIDENCE`), `unsure` (below it), `not_stated`
  (not stated or not combined directly), or `picked`.
- A disagreement adds one question to the pass's card
  (`domain/strategy/operator_questions.py`): keep FRAME's operator or use the read
  one, each option a `SetOperator` binding over the combine's criteria. The pass
  ends `needs_user` and `OperationalSpec.ready_to_build` is false while the
  disagreement stands. A disagreement the card does not ask, because the researcher
  answered that question, becomes `unsure`.
- A picked option rewrites that combine, every node of its chain included, with no
  model in between (`lead_consult.apply_option_bindings`), and records `picked`. A
  pick is never read again while the combine keeps that operator, and an edit may
  move a held combine to the operator the words read as or the researcher picked
  (`AgentToolState.read_operators`).
- Who chose each operator is shown: the facts part's combine step carries
  `operatorSource` (stated, card or chosen) and the ledger's structure lists each
  combine with its chooser. `agrees` is the researcher's, `picked` the
  researcher's on a card, and every other combine the assistant's.
- When the service does not answer, nothing is recorded and nothing is asked.

A combination requirement a thread recorded before this decision still loads. Its
check finds the criteria that link it and names the operator they meet at, never a
pass or a fail; with no link it abstains. A delete withdraws it when no remaining
criterion links it, like any linked requirement, and the alternative a message adds
beside a held value of a single-valued kind is the reading's `beside` field, not an
include verb.

# Why

A combination requirement was a model's word for what the researcher wrote between
two phrases, and every check of it matched its terms to criteria by shared words;
a wrong operator recorded at reading time was then verified against itself. The
operator a tree joins two branches by is a typed fact of the tree, the branches'
quotes are the researcher's own words, and the question a Decisions call answers
is the one the card would otherwise ask blind. Asking only where both branches
quote the researcher keeps the cost to the combines the researcher's words can
settle.

# Rejected

- **A model-written combination requirement.** It records the reader's operator as
  the researcher's and needs word matching to find its members.
- **Reading connective words.** "and", "or", "but not" and "with" are read wrong in
  both directions; the rules grew per failure and still missed phrasings.
- **Reading the whole history in one question.** When a later message changes how
  two branches combine, one answer over every message has no right reading, and an
  older message outvoted the newest at a confidence over the floor, so an explicit
  edit was held behind a card. Neither is a message's text parsed for an operator.
- **Asking on every combine.** A combine over an assumed definition has no words of
  the researcher to read, and a card on every build asks what the researcher never
  said.

# What would prove this wrong

The batch replay measures FRAME's operator accuracy and how often the reader
disagrees with a correct tree. A false-disagreement rate that asks the researcher on
correct trees, at the threshold the vocabulary pick uses, means the threshold or the
question is wrong. `tests/unit/ai/lead/test_a_combine_is_read_against_the_researcher_s_words.py`
holds the request, the card, the pick and the no-answer path;
`tests/unit/domain/strategy/test_operators_come_from_the_tree.py` the chains, the
readings and the wording; the response in
`tests/fixtures/decisions/operator_reading.json` is written to the service's shape,
not recorded from it.
