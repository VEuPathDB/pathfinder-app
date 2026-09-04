---
type: Decision
title: A value the request already states is not a question
description: Three resolution gaps in one run, all the same shape - the answer was in the criterion text and we asked anyway, or invented one. Polarity, vocabulary-less identifiers, and an EC wildcard the accession regex could not match.
tags: [agents, parameters, correctness]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/fable-5, at: 2026-08-17T00:00:00Z }
status: stable
---

# The rules, as first implemented (deleted 2026-08-17)

**Read the amendment at the end first: every rule named in this section is
deleted, and the principle is now carried by the model rather than by our code.**
The section is kept as written because the three failures are what the principle
is made of, and they are the cases any replacement has to survive.

Three separate failures on a multi-criterion request, all reducible to: the criterion
text carried the answer, and resolution either asked for it or made one up.

## 1. Polarity

`GenesByOrthologs.isSyntenic` is a vocabulary of exactly `['yes', 'no']`. The
request said "non-syntenic orthologs". Nothing mapped the phrasing to the
vocabulary, so the model supplied its own wording and WDK answered
`Parameter 'isSyntenic' does not accept 'Non-syntenic'`.

The param name carries the concept (`isSyntenic` -> "syntenic") and the text
carries the polarity, so `_boolean_polarity` reads both. Silence still resolves
to nothing: a criterion that never mentions synteny leaves the param to its own
default rather than picking a side.

## 2. An identifier with no vocabulary to check it against

`GenesByEcNumber.ec_wildcard` is a visible required `string` with no vocabulary
and the placeholder default `'N/A'`. Refusing that default is right. Asking the
user to confirm the `2.7.-.-` they had already written is not.

`accession_in_text` recognized the shape but only matched against vocabulary
options, so a param with no options could never be answered by it.
`sole_identifier_in_text` handles that case: with nothing to validate against,
the literal in the request is the value and WDK is what checks it. Two
identifiers in one criterion stays a question -- guessing which one a param
wants is how `PF00069` once became a phosphofructokinase domain.

## 3. The regex could not match the most common EC form

`_ACCESSION_RE` ended in `\b`. An EC wildcard ends in a hyphen, and `\b` requires
a word character before it, so `2.7.-.-` matched nothing at all -- in this rule
and in every other caller of that regex. The trailing boundary is now a
lookahead.

# Why they are recorded together

Individually each looks like a small parsing miss. Together they are one
principle the resolver was not applying: **a value the user stated is not a
question, and it is not an invitation to guess either.** The two failure modes
are symmetric, and both were present in a single run.

# Evidence at the time

Observed: same prompt, across three runs:

| run | outcome |
|---|---|
| before | FRAME exhausted its 60-call budget; nothing built |
| after polarity + partial-progress | FRAME completed; BUILD stopped on `ec_wildcard` |
| after the identifier rule | FRAME reports **0 open questions**; `ec_wildcard` resolved |

# What was still asked, correctly

`ms_assay` -- the request says "trophozoite samples" without naming a WDK
experiment, so there is a real choice only the user can make. That question was
the system working, and the same parameter is still where a proposer
under-selects.

# Measured at the time, and extended

A benchmark over the verified gold strategies scores every parameter as exact,
wrong, asked or unset, and splits the wrong ones by provenance. That split is
the number that matters: a value the search defaulted is disclosable, while a
value we claim the request stated and got wrong is a result nobody can check.
The benchmark survives; the arms below do not, and the amendment says what
replaced them.

The stated-wrong count went from nine to zero across three fixes, each a value
bound to a parameter that could not hold it:

- a strain name matched the accession shape, so it bound to a numeric bound; the
  rule was changed to refuse a non-numeric literal on a numeric param
- a contrast written "A vs B" bound B as the comparator, because a substring
  match took the longest name anywhere in the text rather than the one on the
  comparator side; the fold change was therefore inverted
- a search that offers both a real vocabulary and a spare string field had the
  identifier taken by the string field; the rule was changed so that the
  vocabulary listing a value owns it

The quoted-term rule closed the mirror case: a term the request put in quotes
answered the search's own free-text query, where before it had been asked back.

# Amended 2026-08-17

**The principle is kept and every rule named above is deleted.** `_boolean_polarity`,
`accession_in_text`, `sole_identifier_in_text` and the quoted-term rule are gone
with the rest of the text-reading tier
([one proposer, one validator](one-proposer-one-validator.md)). The three
failures in this file are now the model's to avoid, and it has what the rules
never had: the whole parameter list, each parameter's help and vocabulary, and
one call in which to answer all of them. On the same corpus the rules bound 13
of 332 values; the proposer states 222.

Two pieces of this file outlived their rules. `_ACCESSION_RE`, whose trailing
lookahead is described above, is still what makes `_states_a_quantity` see a
number written as an EC wildcard. And the principle now has an enforcement it
did not have then: a numeric parameter left null while the criterion states a
quantity that is not the default comes back as `unread`, and `set_criterion`
refuses the call rather than defaulting quietly.

# Anchor

`services/catalog/param_dag.py:_states_a_quantity`, guarded by
`tests/unit/services/catalog/test_param_dag_defaults.py`.
