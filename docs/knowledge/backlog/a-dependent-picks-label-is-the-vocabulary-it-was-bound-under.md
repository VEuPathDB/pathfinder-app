---
type: Backlog
title: A dependent pick's label is the vocabulary it was bound under
description: A dependent pick is labelled on the vocabulary its own parents answer on the bind, on hydration and on replay; the site-default count still reads a dependent pick at the published default, unmeasured until a recording shows a published default its bound parents do not list.
tags: [parameters, frame, hydration, wdk]
generated: { by: claude-code/opus-5.5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# A dependent pick's label is the vocabulary it was bound under

**What is known.** `set_criterion` builds each `BoundValue` through
`operational_spec.bind_values` on `sheet_params.vocabularies_under`: the
published sheet with each dependent vocabulary taken from a read under the
bound parents. `pick_readings.site_default` counts a dependent pick at the
published default, which the bound-parent vocabulary may not hold.

**What is measured.** plasmodb `GenesByInterproDomain`, `domain_typeahead`
(`vocab_depends_on`: `organism`, `domain_database`), read live with
`domain_database = Pfam`: the published read (default organism Haemoproteus
tartakovskyi strain SISKIN1) holds 1,509 entries; the read under Plasmodium
falciparum 3D7 holds 2,102, of which 665 the published read lacks (PF00013,
PF00051, PF00084, ...) and 72 it holds that the 3D7 read lacks.

**Done.** A value the spec already holds keeps the label it was bound under when
hydration or replay reads it again on the published sheet
(`value_binding.read_again`), so a Pfam domain bound for 3D7 keeps "KH domain"
(`tests/fixtures/wdk/search_genes_by_interpro_domain_under_pf3d7_pfam.json`, a
production recording now held in `fixtures-production-backup-2026-10-09/` until
QA re-records it).
A value first read from a strategy (a step the site edited, moved onto another
search or added, and a hydrated strategy) is labelled on the sheet its step's
own parents answer: `sheet_params.sheets_under_their_parents` reads that sheet
once for each step whose dependent pick has a parent other than the published
value (`value_binding.parents_moved`), and `spec_hydration.read_under_their_parents`
reads the criterion again on it.

**What remains.**
- `pick_readings.site_default` counts a dependent pick at the published default.
  The `GenesByInterproDomain.domain_typeahead` default is `[]`, so it counts
  nothing there; a dependent pick whose published default is a term its bound
  parents do not list has not been found yet, and finding one is the first step.

**Done when.** A recorded dependent pick with a non-empty published default
shows whether the site-default count needs the bound-parent vocabulary.
