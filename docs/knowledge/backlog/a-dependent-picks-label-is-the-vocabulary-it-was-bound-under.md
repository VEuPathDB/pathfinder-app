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

**What is measured.** plasmodb `GenesByInterproDomain`, `domain_typeahead`
(`vocab_depends_on`: `organism`, `domain_database`), read live with
`domain_database = Pfam`: the published read (default organism Haemoproteus
tartakovskyi strain SISKIN1) holds 1,509 entries; the read under Plasmodium
falciparum 3D7 holds 2,102, of which 665 the published read lacks (PF00013,
PF00051, PF00084, ...) and 72 it holds that the 3D7 read lacks. A Pfam domain
bound for 3D7 is labelled on the bind and unlabelled on hydration and replay.

**Done.** A value the spec already holds keeps the label it was bound under when
hydration or replay reads it again on the published sheet
(`value_binding.read_again`), so a Pfam domain bound for 3D7 keeps "KH domain"
(`tests/fixtures/wdk/search_genes_by_interpro_domain_under_pf3d7_pfam.json`).

**What remains.**
- A value first read from a strategy, such as a step the site edited
  (`spec_replay.criterion_rebound`), is labelled on the sheet
  `services/strategies/sheet_params.sheet_params_for_searches` reads with no
  context, so a dependent pick only its bound parents list has no label. The fix
  reads each such step's sheet under its own parent values (the
  `_frame_measure.vocabularies_under` read) before replay binds it.
- `pick_readings.site_default` counts a dependent pick at the published default.
  The `GenesByInterproDomain.domain_typeahead` default is `[]`, so it counts
  nothing there; a dependent pick whose published default is a term its bound
  parents do not list has not been found yet, and finding one is the first step.

**Done when.** A test builds the same dependent pick through a site edit's replay
and gets the label the bind gives, and a recorded dependent pick with a non-empty
published default shows whether the site-default count needs the bound-parent
vocabulary.
