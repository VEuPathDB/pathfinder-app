---
type: Backlog
title: An "all" over many genomes is asked about
description: A requirement that a gene or ortholog group be present in every member of a clade with many strains and incomplete assemblies is bound as written; the turn asks first whether "all" means every genome, a share such as 90%, or every species with most strains of the best-sampled one.
tags: [frame, consult, orthomcl, phyletic, requirements]
generated: { by: claude-code/opus-5, at: 2026-10-21T00:00:00Z }
status: proposed
---

# An "all" over many genomes is asked about

## What happens

On OrthoMCL, "Which ortholog groups are present in all Plasmodium species but absent
from Toxoplasma gondii?" builds a phyletic pattern that requires all 61 Plasmodium
genomes (`padl+pber+...+pyoy=61T AND tgar+...+tgve=0T`). The site holds many
P. falciparum strains and several incomplete assemblies, so a group missing from one
draft genome is dropped although it is conserved. The turn binds "all" as written and
does not ask.

The absence half does not have this problem: an incomplete genome that lacks a gene
does not reject a valid group.

## Change

1. When a presence requirement covers a clade whose member genomes number more than a
   few, or include strains of one species, the turn asks once (consult) with three
   offers: every genome; at least a share of the genomes (90% by default); every
   species, counting a species present when most of its strains are.
2. An absence requirement over the same clade is bound without asking.
3. The question names the counts it is about (the number of genomes, and the species
   that have several strains with their strain counts) from the taxonomy the phyletic
   lookup already reads.

## What the builder takes

`build_phyletic_expression` (veupathdb-mcp 0.2.0b40) writes each offer from a pattern:
every genome is a `count` of `genomes` `exactly` N over the clade's codes, a share is a
`count` with measure `share` and condition `at_least` (90 percent of 61 genomes is at least 55),
and every species is a `count` over `each_species_of` the clade. No offer needs an
expression written by hand.

## Done when

The example question reaches the consult with the three offers and the counts, each
offer builds a strategy whose expression matches it, and a replay or unit test covers
the presence and absence cases.
