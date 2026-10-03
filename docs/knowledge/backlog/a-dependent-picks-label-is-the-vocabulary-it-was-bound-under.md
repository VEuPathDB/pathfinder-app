---
type: Backlog
title: A dependent pick's label is the vocabulary it was bound under
description: The bind labels a dependent pick against the vocabulary read under its bound parents, while hydration and replay label it against the published vocabulary, so one value may carry a label on one path and none on another; unmeasured until a recording shows the two vocabularies differ.
tags: [parameters, frame, hydration, wdk]
generated: { by: claude-code/opus-5.5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# A dependent pick's label is the vocabulary it was bound under

**What is known.** `set_criterion` builds each `BoundValue` through
`operational_spec.bind_values` on `_frame_measure.vocabularies_under`: the
published sheet with each dependent vocabulary taken from a read under the
bound parents. Hydration (`spec_hydration.sheet_marked`) and replay
(`spec_replay.criterion_restated`, `criterion_rebound`) read the sheet from
`services/strategies/sheet_params.sheet_params_for_searches`, which reads the
search definition with no context. For a parameter with `vocab_depends_on`,
an entry that only the bound-parent vocabulary holds therefore gets a `label`
on the bind and an empty `label` on hydration and replay.
`pick_readings._site_default` has the same shape: it counts a dependent pick
at the published default, which the bound-parent vocabulary may not hold.

**What is not measured.** No recorded pair shows a dependent vocabulary that
changes with its parents. The giardiadb GenesByText context read
(`search_giardiadb_genes_by_text_under_context`) holds the same 27
`text_fields` entries as the published read.

**Recording that settles it.** plasmodb `GenesByInterproDomain`,
`domain_typeahead` (`vocab_depends_on`: `organism`, `domain_database`),
read under two organisms with `domain_database = Pfam`. The published read
holds 1509 Pfam entries under the default organism. Record the definition
under a second organism (for example `Plasmodium falciparum 3D7`) and list
the entries one read holds and the other does not.

**Rule expected.** The label is read from the vocabulary the value was bound
under, carried on the `BoundValue`, and never derived again: hydration and
replay of a value the spec already holds keep its label, and a value first
read from a strategy is labelled under its own bound parents.

**Done when.** The recording is under `tests/fixtures/wdk`, a test builds the
same dependent pick through the bind, hydration and replay paths and gets the
same `label`, and `_site_default` counts a dependent pick at a value the
bound-parent vocabulary holds.
