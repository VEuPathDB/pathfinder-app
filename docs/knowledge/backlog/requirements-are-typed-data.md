---
type: Backlog
title: Requirements are typed data
description: Every decision the thread makes about a requirement (who stated it, what it replaces, what a withdrawal or a delete retires, what an answer drops, how the verdict compares it) reads words, phrases or regexes in model-written values. Give each requirement a typed value discriminated by kind, beside its stable id, its verbatim quote and the links from the criteria that answer it, and move each decision onto those fields, kind by kind, in the steps that remain.
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

`Criterion.answers` and the paths that read it are built
([a criterion links the requirement it answers](../decisions/a-criterion-links-the-requirement-it-answers.md)).
A requirement is `Constraint` with a typed `value`, a union discriminated by
`kind`
([a requirement carries a typed value of its kind](../decisions/a-requirement-carries-a-typed-value-of-its-kind.md));
`percentile` (end and share), `fold_change` (cut, scale, direction),
`significance` (statistic and an upper bound), `organism` (a site vocabulary
entry,
[an organism requirement holds a site entry](../decisions/an-organism-requirement-holds-a-site-entry.md)),
`data_type` (`rna_seq`, `microarray`), `record_type` (a record class the site
lists, role `answer` or `through`) and `untyped` (text) are built. The kinds
still to gain a member: `count` (feature, operator, value), `ortholog`
(organisms, syntenic), `text` (phrase, exact) and `property` (phrase). No kind
states how
requirements combine: the operators are FRAME's tree, read against the
researcher's words
([operators come from FRAME's tree](../decisions/operators-come-from-frames-tree.md)).
A value kind is compared only through a link that names a parameter. Single-valued
kinds replace by kind, unless the reading states the new value beside the held
one; property, text, count, ortholog and untyped hold many values. A requirement
with no value, stored before or of a kind not migrated yet, is untyped and shows
"not verified"; no shim keeps an old shape.

## Steps

Each step is test first and runs every gate. A step marked R changes classifier
or FRAME behaviour, so before it is pushed the eval cases that passed before must
pass on Luna on QA, and a case that flips is rerun three times per arm.

13. Count, ortholog, text, property and untyped; `other` is removed; the "not
    verified" display (R). `merge_constraints._dimension` and
    `phrasings_the_request_states` read typed fields.
14. Names: a generated name stores its seed (step id to parameter and wire value)
    and is outdated when a seed value or step is gone; a step name PathFinder made
    is regenerated from the search display name and bound labels, and a name the
    researcher wrote is never rewritten. Not R.
15. Cleanup: delete `message_states` and `content_words` with their tests; run
    vulture; update the verdict's kind table, the requirement lifecycle decision
    and the vocabulary convention; regenerate the shared types and update the web
    constraints section.

## Open

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
