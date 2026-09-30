---
type: Backlog
title: A dataset search's organism is a catalog mark
description: A search that publishes no organism parameter, as every expression dataset search does, has no organism scope, so an INTERSECT of it with a search on another species is not refused and returns 0 by construction; the tool server reads the organism from the dataset the search runs on and the host holds it on the criterion.
tags: [frame, orthology, catalog, veupathdb-mcp]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# A dataset search's organism is a catalog mark

**What I did.** On cryptodb, bound `GenesWithSignalPeptide` at organism
"Cryptosporidium meleagridis strain UKMEL1" and
`GenesByRNASeqchomTU502_Widmer_oocysts_ebi_rnaSeq_RSRCPercentile` (the
C. hominis TU502 oocyst percentile search) and stated their INTERSECT.

**What I got.** The structure was accepted. The signal peptide search returns
421 `CmeUKMEL1_*` genes, the percentile search 783 `Chro.*` genes at percentile
80, 3,886 at 0 and 792 with protein coding "all"; each overlap with the 421 is
0.

**Why that's wrong.** Gene ids of two species never match, so the combine is
0 by construction, and every widening leads to 0 too. The researcher spends a
turn on a dead choice where a `Transform by Orthology` of the C. hominis arm to
UKMEL1 answers the question.

**Why it happens.** `domain/strategy/validate.py::cross_organism_refusal`
reads each side's organism from the parameter its search marks as the
organism (`Criterion.organism_param`). The percentile search publishes none
(its parameters are `profileset_generic`, `samples_percentile_generic`, the
percentile bounds, `any_or_all`, `protein_coding_only`, `channel`), and WDK's
own `properties.organisms` on it is a fixed list of three species. So the
scope is unknown and the check abstains. Refusing every unknown scope beside
a known one is not a fix: the corpus cases `uat-dry-d-amoebadb`,
`uat-dry-b-tritrypdb` and `uat-dry-d-vectorbase` each intersect a dataset
search with a search on the same organism, and they are right.

**Fix.** The tool server reads the organism of a dataset search from the
dataset it runs on (the dataset record's organism, keyed by the dataset name
the search's question carries) and returns it as a typed field of the search
detail, the way it marks the organism parameter. The host holds it on
`Criterion` at bind, and `extract_output_organisms` reads it for a leaf whose
search marks no organism parameter. A veupathdb-mcp tag, then the pin bump.

**What you'd get.** The INTERSECT is refused at `set_structure` with a
transform of the C. hominis arm to UKMEL1 as the remedy, and the three
same-organism corpus cases still build.
