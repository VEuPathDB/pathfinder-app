---
type: Decision
title: A gene set shows where its genes live
description: A saved gene set records, for each saved id, the gene and the genomics site that holds it, and a site lists every set with genes there - its own site, each home site with that site's genes, the portal and OrthoMCL with every gene. A set of records that are not genes stays on its own site. Keeping every set on the site it was saved on, and translating ids between any two sites, were rejected.
tags: [gene-sets, sites, orthomcl, portal]
generated: { by: claude-code/opus-5.5, at: 2026-10-15T00:00:00Z }
status: stable
---

# What was decided

A WDK strategy runs on one site, and a conversation is bound to one site. A
question can still need two sites: a count across species is OrthoMCL's
`GroupsByPhyleticPattern`, and the expression data that narrows the result is
PlasmoDB's. A saved gene set carries the genes from one to the other.

**Each set records its genes' homes.** `GeneSet.homes` maps each saved id to a
`GeneHome` (the gene id on its genomics site, and that site), filled when the set
is saved or refreshed (`services/gene_sets/homes.py`):

- a genomics site's set of genes holds that site's own genes;
- a portal set reads each gene's `project_id`;
- an OrthoMCL protein set reads `gene_source_id` and `gene_source_url`, whose host
  names the site. A protein whose source is not a VEuPathDB site has no home.

A list saved without a step is read through the site's id-list search
(`GeneByLocusTag` on genomics sites and the portal, `ByIdList` on OrthoMCL). A
set of records that are not genes, such as ortholog groups, has no homes.

**One rule lists them** (`domain/gene_homes.py::genes_on`). The site a set was
saved on reads the ids as saved. The portal and OrthoMCL read every gene. A
genomics site reads its own genes. A site lists a set when it reads at least one
id, and the list reports how many (`geneCountHere`).

**A set starts a criterion through the site's id search.** `set_criterion` takes
`gene_set` in place of `search_name`; the genes the site reads become an id-list
dataset bound to `GeneByLocusTag` (`ds_gene_ids`) or `ByIdList` (`source_ids`).

# What was rejected

- **Every set stays on its own site.** The OrthoMCL to PlasmoDB question then has
  no path inside PathFinder: the researcher copies ids out of one site and pastes
  them into the other, and an OrthoMCL protein id (`PF3D7_1352300.1-p1`) does not
  resolve on PlasmoDB.
- **Translate ids between any two sites.** Genomics sites share no genes, so a set
  from one has nothing to translate to on another; across organisms, orthology is
  the portal's transform, not an id lookup.
- **Parse a protein id into its gene id.** A gene id may hold a dot itself
  (`Tb927.10.1234`); OrthoMCL states the gene in its own column.
