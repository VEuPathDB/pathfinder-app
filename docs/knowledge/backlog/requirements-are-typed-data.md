---
type: Backlog
title: Requirements are typed data
description: Every decision the thread makes about a requirement (who stated it, what it replaces, what a withdrawal or a delete retires, what an answer drops, how the verdict compares it) reads words, phrases or regexes in model-written values. Replace Constraint.requested_value with a discriminated union of typed requirements, each with a stable id, a verbatim quote and links from the criteria that answer it, and move each decision onto those fields, kind by kind, in fourteen steps.
tags: [agents, lead, frame, verification, requirements, redesign]
generated: { by: claude-code/opus-5.5, at: 2026-11-01T00:00:00Z }
status: proposed
---

# Requirements are typed data

## Why

The principle: no decision in code rests on words, phrases or regexes in text a
model wrote; it rests on typed data. A requirement today is a `Constraint`
(`domain/strategy/constraints.py`): a kind and a model-written `requested_value`.
Attribution, displacement, withdrawal, stand-ins, delete retirement, the drops of
picked, asked and compared values, the combination's terms and every value
grounding read that string. An offline replay of the current functions over the
saved runs (522 conversations, 1,018 classifications) measured the lifecycle and
attribution paths: 60 distinct requirements the researcher stated were marked
assumed, six withdrawn requirements stayed live, every requirement of two requests
phrased as questions was dropped, and five delete or side retirements kept a
requirement whose step was gone. The decisions this work builds, with the
measurement, are
[a requirement is the researcher's when it quotes their words](../decisions/a-requirement-is-the-researchers-when-it-quotes-their-words.md),
[a withdrawal names a held requirement by its number](../decisions/a-withdrawal-names-a-held-requirement-by-its-number.md) and
[an unlinked requirement is not verified and never blocks](../decisions/an-unlinked-requirement-is-not-verified-and-never-blocks.md).
These stand and are not reopened: the computed verdict, a refusal resting on typed
state, a pass naming a requirement by its number, a picked reading standing in for
its words, a reading saying who chose it, and a saved conversation outliving its
build.

## The model

A new `domain/strategy/requirements.py` holds `Requirement`, a union discriminated
by `kind`. Every member carries `id` (minted by `ThreadRequirements`, never written
by a model), `ref` (its number inside one classification), `source` (`stated` or
`assumed`), `quote`, `hard` and `label` (display only). The kinds: `organism`
(a site vocabulary entry), `record_type` (a WDK `recordClassName`, role `answer` or
`through`), `data_type` (`rna_seq`, `microarray`), `percentile` (end and share),
`fold_change` (cut, scale, direction), `significance` (statistic and an upper
bound), `count` (feature, operator, value), `comparator` (two sides), `ortholog`
(organisms, syntenic), `text` (phrase, exact), `property` (phrase), `combination`
(`AND` or `OR` over at least two member refs) and `untyped` (text).
`Criterion.answers` lists `RequirementLink`s (a requirement id and an optional
parameter), set by FRAME in `set_criterion`. `UserIntent` carries `requirements`,
`withdrawn` as held numbers, and `differential_sides` as refs. A value kind is
compared only through a link that names a parameter; a percentile's end is read
from the site's parameter name. Single-valued kinds replace by kind; property,
text, count, ortholog, combination and untyped hold many values. A stored
requirement of the old shape reads as `untyped` and shows "not verified" until
restated; no shim keeps the old shape.

## Steps

Each step is test first and runs every gate. A step marked R changes classifier
or FRAME behaviour, so before it is pushed the eval cases that passed before must
pass on Luna on QA, and a case that flips is rerun three times per arm.

2. Stable ids replace `kind:value` keys: `ThreadRequirements` mints them, and
   `ReplacedLifecycle.by`, `AcceptedReading` replaces, `record_roles`,
   `SiteCheck.requirement` and `TurnRecord.requirements_added` carry ids. The
   stored-state migration reads an old requirement as untyped and drops a stored
   `site_verdict` for recomputation; an integration test resumes a checkpoint the
   current build wrote. Not R.
3. Links (R): `Criterion.answers`. A stand-in question carries requirement
   numbers and `_ASKS_A_STAND_IN_RE` goes (`requirement_lifecycle.stood_in_for`);
   a delete retires the requirements whose only linking criteria it removed and
   withdraws a combination that lost every member link (`retire_dropped_sides`,
   `thread_requirements._stated`); `spec_fold.restated_requirement`,
   `questions.with_withdrawals` and the gap rows (`requirement_naming`,
   `caveats.check_gaps`) read ids.
4. Combination typed (R): displacement by a shared member id, grounding through
   member links (abstain with no link), `lead_consult._answer_requirement` takes a
   typed combination, the FRAME floor is the member count and the allowed
   operators come from the typed field. Delete `match_terms`, `_best_match`,
   `CombinationRequest.parse` and `combination_terms_overlap`.
5. Withdrawal by number (R): `withdrawn_by` and `with_recorded_sources` read held
   numbers mapped to ids.
6. Attribution by quote (R): `attributed`, the include-verb arm,
   `message_states_constraint` and `_span` give way to the quote rule and the
   connective reading between members' quotes; a pick binds an option id, asks are
   a typed list with no overlap test (`_only_asked`, `researcher_asks`), sides are
   refs (`_no_side_is_a_constraint`), and `value_source.cut_from` compares the
   quote with the bound value by equality.
7. Percentile (R): compared through its link; delete `PercentileRequest.parse`.
8. Fold change (R): cut, scale and direction against the linked parameter or the
   analysis effect size; `fold_grounding` reads no words.
9. Significance (R): the bound against the linked parameter or the analysis
   threshold.
10. Data type (R): against the data marks of the linking criteria.
11. Organism (R): a vocabulary entry compared by equality in grounding, the
    organism check, FRAME's bind refusal, the organism drop and `gene_record`'s
    `ortholog_organism`; `complete_organisms` becomes gate validation, and a
    non-entry goes to a Decisions choice over the site's entries, asked on a card
    when it does not settle.
12. Record type (R): equality with `recordClassName`, gene to transcript or
    sequence by a typed table; `constraints._a_value_of_a_record_is_no_record_type`
    and `requirement_checks.classes_named` go.
13. Count, ortholog, text, property and untyped; `other` is removed; the "not
    verified" display (R). `merge_constraints._dimension` and
    `phrasings_the_request_states` read typed fields.
14. Names: a generated name stores its seed (step id to parameter and wire value)
    and is outdated when a seed value or step is gone; a step name PathFinder made
    is regenerated from the search display name and bound labels, and a name the
    researcher wrote is never rewritten. Not R.
15. Cleanup: delete `message_states`, `states_the_content`, `content_words`,
    `message_states_constraint`, `record_noun`, `qualifies_a_record_noun`,
    `requirement_naming` and `names_a_retired_requirement` with their tests; run
    vulture; update the verdict's kind table, the requirement lifecycle decision,
    the operator section of the strategy-answers-to-a-spec decision and the
    vocabulary convention; regenerate the shared types and update the web
    constraints section.

## Open before step 2

- The typed gold set: its size and the pass threshold for typed accuracy
  (`ExpectedOutcome.requirements` on the first turn of each corpus case that
  states requirements, scored by field equality).
- Whether `property` and `text` merge.
- The Decisions price per call on the Luna endpoint, which the model catalog does
  not hold yet.

## Done when

No function under `apps/api/src/pathfinder` decides a requirement's source,
lifecycle, drop or check from the words of a model-written value; the functions
named in step 15 are gone; a replay of the saved runs under the new schema
reports the typed accuracy, the untyped share and the share of quotes no message
holds; and the eval cases that passed before step 2 pass.
