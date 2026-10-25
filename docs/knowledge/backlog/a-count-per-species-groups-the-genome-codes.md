---
type: Backlog
title: A count per species groups the genome codes of each species
description: Asked to aggregate a per-genome tally to species, an edit replaced the taxonomy step with a phyletic filter that every species must meet, which no group of one protein can, and the result emptied; a correct answer counts the result step by genome code and sums the codes of each species from the site's taxonomy.
tags: [lead, frame, tally, orthomcl]
generated: { by: claude-code/opus-5.5, at: 2026-10-25T00:00:00Z }
status: proposed
---

# A count per species groups the genome codes of each species

## What I did

Rerun 3, run A, on QA OrthoMCL, one turn at a time:

1. "Which Plasmodium species has the most singleton genes, meaning genes in a
   group of their own?" The turn built `GroupsBySequenceCount` (all_count 1..1),
   the `FromGroups` transform and an INTERSECT with `ByTaxonomy` over the 61
   Plasmodium genome codes: a root of 2,744 proteins.
2. "Aggregate the strains to species level."
3. The answer "Keep Plasmodium species" on the card that followed.

## What I got

Turn 2: the edit dropped the taxonomy criterion and bound
`build_phyletic_expression` {count, each_species_of all 61 codes, genomes,
at_least 1}, 2,753 groups, intersected with the groups of one protein before the
transform. Turn 3 put the taxonomy step back: singleton groups INTERSECT the
phyletic filter = 0, transform = 0, root = 0. The reply: "no Plasmodium species
can be ranked from this strategy."

## Why that's wrong

The researcher asked for the turn-1 tally summed by species. The phyletic filter
keeps groups present in every species, and a group of one protein holds one
genome, so the filter and the question exclude each other. The strategy ends at
0 proteins and the question goes unanswered, though the turn-1 strategy already
holds every record the answer counts.

## Why it happens

No tool groups a tally's values. `count_step_by_column` counts the result step by
genome code (`abbreviation`), and nothing maps each code to its species, so FRAME
reads "aggregate to species" as a search criterion and binds the nearest one.

## Fix

Not chosen. A correct answer needs:

- the result step counted by genome code, as turn 1 counted the taxonomy step;
- each genome code mapped to its species from the site's taxonomy, the tree the
  `ByTaxonomy` parameter and the phyletic codes read, not from the genome names;
- the codes of each species summed, with the codes each species holds shown, so
  a species with more sequenced strains is seen to count more genomes;
- the Lead's rules naming an aggregation of a tally as a read of the tally, never
  an edit of the strategy.

## What you'd get

The same 2,744-protein strategy, and a table of species, each with its summed
count and its genome codes, the leader named with its count.
