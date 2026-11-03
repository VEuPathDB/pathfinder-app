---
type: Decision
title: A requirement carries a typed value of its kind
description: Constraint stays the requirement record and gains an optional value, a union discriminated by kind whose members hold the typed fields of each kind, held to the requirement's own kind by a validator. The message reading writes it; percentile, fold change and significance are compared through it against the parameter or the analysis cut their linking criterion names, a data type against what the site marks its linking criteria run on, and a record type by equality with the class of the result step or of a step the tree passes through. Twelve requirement classes in place of Constraint were rejected.
tags: [requirements, verification, lead, frame]
generated: { by: claude-code/opus-5.5, at: 2026-11-03T00:00:00Z }
status: stable
---

# What was decided

`Constraint` (`domain/strategy/constraints.py`) keeps its id, kind, source, quote,
hard flag, label and `requested_value`, which is display only. It gains `value`,
a `RequirementValue` or null. `RequirementValue` is a union discriminated by
`kind`; the members built so far are:

| Member | Kind | Fields |
|---|---|---|
| `PercentileValue` | `percentile` | `end` (`top`, `bottom`), `share` (above 0, at most 100) |
| `FoldChangeValue` | `fold_change` | `cut` (a number, or null for a direction alone), `scale` (`fold`, `log2`), `direction` (`up`, `down`, `either`) |
| `SignificanceValue` | `statistical_threshold` | `statistic` (`p_value`, `adjusted_p`, `fdr`, `q_value`, `unspecified`), `at_most` (above 0, at most 1) |
| `DataTypeValue` | `data_type` | `data` (`rna_seq`, `microarray`) |
| `RecordTypeValue` | `record_type` | `record_class` (a record class the site lists, by its name in the catalog), `role` (`answer`, `through`) |
| `UntypedValue` | `other` | `text` |

A model validator refuses a value whose kind is not the requirement's. The
other kinds gain their members with the steps that migrate them. A requirement
with no value, stored before the field existed or of a kind not migrated yet, is
untyped.

The message reading writes the value. `StatedRequirement`
(`domain/message_reading.py`) is a union discriminated by the reading's `kind`;
the percentile, fold-change and significance members carry the same fields, and
`intent_of` copies `typed()` onto the requirement. "No fold-change cutoff" is a
cut of 1 on the fold scale. The extraction reads the record classes the site
lists (`ReaderInput.record_classes`, from the catalog), and a record type whose
class the site does not list is kept as an untyped requirement with its quote
(`StatedRequest.within`); no class is guessed for it.

Percentile, fold change and significance are compared only through a link
(`domain/strategy/value_grounding.py`, `fold_grounding.py`, `linked_values.py`):

- the parameter a linking criterion's `RequirementLink.param` names, as the site
  binds it, and the cut of the analysis a linking criterion runs;
- a percentile's end is read from the site's parameter name: a `min` parameter
  holds the lower bound, which a top share sets, and a `max` parameter the upper;
  a linked bound at the other end must hold the full scale;
- a fold cut is compared on the scale the parameter's display name or the
  compute's effect size label names, and a stated direction against the
  analysis's effect direction;
- every linked value must agree; one that does not is a substitution.

A data type is compared with what the site marks each criterion that links it
runs on (`DataMarks.run_on`: the type of its upload, else the assay of its study
or its search): grounded when one runs on the stated data, substituted when they
run only on the other, ungroundable when none runs on expression data, and
provisional while a linked analysis has not run. A record type is compared by
equality (`domain/requirement_checks.py::record_type_check`): an `answer` with the
result step's class, a `through` with the class of any step of the tree. One typed
table widens a class: `gene` is answered by `transcript` and by OrthoMCL's
`sequence`. The role is the reading's
([a record type's role is read with its class](a-record-types-role-is-read-with-its-class.md)).
The briefing a turn opens with regrounds each requirement on the answered and
the live tree through the links the thread's spec holds, by step id.

No link with a parameter or an analysis cut, no linking criterion for a data
type, or no value, gives the "not verified" path: grounded with no realized value, so the check is unchecked and
never passes or blocks
([an unlinked requirement is not verified and never blocks](an-unlinked-requirement-is-not-verified-and-never-blocks.md)).
Once a search is bound, a stated value no criterion links is offered for
withdrawal on FRAME's card (`frame_requirements.requirements_no_search_states`).

# Why

The grounding read the model's `requested_value`, and once its quote, with
regexes (`PercentileRequest.parse`, the significance number scrape, the fold
number and no-cut words), and took the strategy's percentile, significance or fold
parameter by its name wherever it stood. A value worded another way grounded
another way or blocked, and a parameter no criterion bound for the requirement
could pass it. The reading already writes a structured request, so the fields
cost one schema and no extra call. On the eight labelled corpus turns that state
these kinds (ten requirements), two runs on Luna matched the hand label on 39 of
the 40 typed fields of the requirements they extracted; the one miss took an up
direction from an earlier message. For the data and record types the grounding
read the words of the value: an RNA-Seq pattern, and the record nouns of the
value matched against the site's display names, which also turned a record type
that qualified a gene noun into another kind. On 21 labelled corpus first turns
(14 OrthoMCL record-type turns with 16 requirements, two data-type turns, five
genomics turns that state neither), two runs on Luna with the final guide
extracted 27 of the 32 record types and all four data types, and every field of
every one extracted matched the hand label (record class, role, data); the
misses were record types left out. Two earlier runs showed two faults the guide
now addresses: words naming an organism and a class together were read as the
organism alone, and a protein the wanted groups contain was read as a class the
tree passes through, which would fail a correct group strategy.

# What was rejected

**Twelve requirement classes in place of `Constraint`.** The first shape of the
plan. It touches every holder of a requirement at once (the thread, the
lifecycle, the ledger, the checkpoints and the web) for the same data, and no
kind could migrate alone. A value on the existing record lets each kind move in
its own step, and a stored requirement loads unchanged as untyped.

**A value field per kind on `Constraint`.** Each kind would add nullable fields
to every requirement, and nothing would hold a field to its kind.

**Keeping the patterns as a fallback when no value is held.** A requirement
the patterns read is exactly one the type did not settle; grounding it by words
is the fault the type removes.

# Anchors

`domain/strategy/constraints.py`, `domain/message_reading.py`,
`ai/lead/message_intent.py`, `ai/lead/message_reader.py`,
`ai/prompts/stated_request.md`, `domain/strategy/linked_values.py`,
`domain/strategy/value_grounding.py`, `domain/strategy/fold_grounding.py`,
`domain/strategy/constraint_grounding.py`, `domain/requirement_checks.py`,
`ai/lead/frame_requirements.py`, `ai/lead/turn_briefing.py`.
