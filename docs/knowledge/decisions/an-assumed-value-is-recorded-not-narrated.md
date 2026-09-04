---
type: Decision
title: An assumed value is recorded, not narrated
description: A value FRAME chooses where the request says nothing is declared on the criterion and rendered as a non-blocking constraint, instead of appearing once in the reply's prose. A contrast half stays a question.
tags: [agents, frame, parameters, ledger]
generated: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
status: stable
---

# What was decided

`set_criterion` takes `assumed`, one entry per parameter the model gave a value
to that the criterion text does not state and that is not the sheet's default.
Each entry carries the parameter name, the value and one sentence of reason.
The entries are stored on `Criterion.assumptions` and the ledger's constraint
section renders each as a `Constraint` with `source = assumed`, `hard = False`
and status `grounded`, the reason as its note. The Lead therefore names them
from the ledger rather than from a sentence it has to remember, and the user
can override any of them by stating the value.

Three refusals guard the input, each a `ModelRetry`: a parameter the search
does not have, a parameter this call left null (there is no value to assume),
and a half of a reference and comparison pair.

# What was rejected

**A defaults-authorisation flag.** The item this closes was filed as "the user
said pick something sensible and nothing hears it". Diagnosis found most of it
was a defect in numeric defaults
([a number's initial value is a default](numeric-default-is-not-an-example.md)),
and the remaining slots now fill from the sheet in the `set_criterion` call
itself. A flag would have gated a mechanism that already runs.

**Filling the slot from a ranked candidate.** The design this was first drafted
against had a resolver that proposed a top candidate per parameter. That
resolver is gone ([one proposer, one validator](one-proposer-one-validator.md)),
so the filling half needs nothing; only the recording half was missing.

**Letting a contrast half be assumed.** Both halves of a reference and
comparison pair defaulted to all samples is a degenerate all-against-all
contrast that returns no differentially expressed genes. There is no defensible
assumption there, so an assumption on such a parameter is refused rather than
recorded.

# Anchor

`AssumedValue` and `Criterion.assumptions` in
`domain/strategy/operational_spec.py`; `_refuse_bad_assumptions` in
`ai/tools/standalone/frame_spec.py`; `assumption_constraints` in
`ai/lead/ledger_sections.py`. Guarded by
`tests/unit/ai/tools/test_frame_spec_sheet.py` and
`tests/unit/ai/lead/test_derive_constraints.py`.
