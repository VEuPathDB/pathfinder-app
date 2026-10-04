---
type: Backlog
title: A study-backed search carries its organism scope
description: An EDA study search has no organism scope, so an intersect of it with a search on another strain is built and returns 0 genes instead of being refused with the orthology remedy.
tags: [organism, eda, structure]
generated: { by: claude-code/opus-5, at: 2026-10-04T00:00:00Z }
status: proposed
---

# A study-backed search carries its organism scope

**What I did.** On toxodb, corpus case `an-edit-to-a-sibling-strain-binds-it`:
built Toxoplasma gondii ME49 genes with a protein kinase Pfam domain intersected
with "Genes higher in 48h bradyzoites than in 24h tachyzoites" (an EDA study
search), 25 genes, then asked to switch the organism to Toxoplasma gondii GT1 on
both steps.

**What I got.** The domain step moved to GT1 (128 genes), the study step stayed on
its ME49 study (1,535 genes), and the intersect returned 0 genes. A run that chose
the ME49 microarray dataset search instead was refused at `set_structure` with the
orthology remedy and built 31 genes.

**Why that's wrong.** A GT1 gene id never equals an ME49 one, so the strategy is
empty by construction and nothing says why.

**Why it happens.** `organism_scope.output_organisms` reads a marked organism
parameter or the organisms of the one dataset that names a search; a study-backed
search has neither, so its scope is unknown and `cross_organism_refusal` abstains.

**Fix.** Read a study-backed search's organisms from its study, as a dataset
search's are read from its dataset.

**What you'd get.** The same refusal and orthology remedy the dataset search gets.
