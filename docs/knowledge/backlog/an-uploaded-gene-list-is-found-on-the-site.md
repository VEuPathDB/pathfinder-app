---
type: Backlog
title: An uploaded gene list is found on the site
description: Asked to use a gene list the researcher uploaded by name, the assistant reads only PathFinder's saved sets and says the list is not available, although the site's gene-list search offers it.
tags: [lead, gene-sets, user-datasets]
generated: { by: claude-code/opus-5.5, at: 2026-11-05T00:00:00Z }
status: proposed
---

# An uploaded gene list is found on the site

## What I did

Ran the corpus case `uat-ud3-plasmodb` on QA PlasmoDB, on Luna, three times through the
worker: "Take the gene list I uploaded, 'pathfinder-uat-genelist', and keep the genes whose
proteins have a predicted signal peptide."

## What I got

All three runs failed, and none used the list. Two left a signal peptide step alone at 30,381
genes and asked which organism the list holds. One reply said:

> I couldn't find `pathfinder-uat-genelist` among the gene lists available on this site

With the same token, the `geneListUserDataset` parameter of `GenesByUserDatasetGeneList`
lists `Ud18NklEhB0wF` with the label `pathfinder-uat-genelist`.

## Why that's wrong

The researcher's list exists on the site, and the assistant tells them to upload it again.
They cannot start from their own list until they find another way in.

## Why it happens

Each run called `list_gene_sets`, which lists PathFinder's saved sets. No tool output in any
run names `geneListUserDataset` or `Ud18NklEhB0wF`.

## Fix

Not decided. A name that no saved set holds is looked up in the site's list of the
researcher's user datasets before the reply says it is missing.

## What you'd get

`GenesByUserDatasetGeneList` on `Ud18NklEhB0wF` intersected with `GenesWithSignalPeptide`,
6 genes as measured on 2026-10-18.
