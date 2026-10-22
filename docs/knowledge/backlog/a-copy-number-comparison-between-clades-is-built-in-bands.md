---
type: Backlog
title: A copy-number comparison between clades is built in bands
description: '"Orthogroups with more genes per genome in Toxoplasma than in Plasmodium" is answered as impossible even after the user gives thresholds, while OrthoMCL''s phyletic expression counts proteins over a list of genomes and can approximate a per-genome ratio as a few count bands joined with OR.'
tags: [orthomcl, phyletic, lead, guidance, copy-number]
generated: { by: claude-code/opus-5, at: 2026-10-21T00:00:00Z }
status: proposed
---

# A copy-number comparison between clades is built in bands

## What happens

"Find orthogroups that have more genes per genome in Toxoplasma than Plasmodium (expanded
gene families)." The turn asks for fixed thresholds; given "2-5 copies in Plasmodium, at
least 2x greater copies in Toxoplasma", it builds a strategy of 10 groups and VERIFY
reports that it uses aggregate counts across the listed genomes, does not enforce the 2x
ratio per orthogroup, and that "the exact comparison remains unavailable in the site's
searches", so the turn ends without the comparison it was asked for.

## What the site can express

`GroupsByPhyleticPattern`'s expression counts taxa (`<list>=<N>T`) and proteins
(`<list>>=<N>`, no `T`) over a list of genome codes joined with `+`
(`lookup_phyletic_codes`, the sheet's grammar help in veupathdb-mcp). A per-genome copy
number for a clade is its protein count over the clade's list divided by the number of
genomes in it, so "Plasmodium 2-5 per genome, Toxoplasma at least twice that" is a short
disjunction of bands, for example with P Plasmodium genomes and T Toxoplasma genomes:
`(PLAS>=2P AND PLAS<3P AND TOXO>=4T) OR (PLAS>=3P AND PLAS<4P AND TOXO>=6T) OR ...`, each
band stating a whole number of copies per genome. The approximation is per clade on
average, not per genome; a group where one strain carries all the copies passes.

## Two genomes compare exactly

Between two single genomes the comparison needs no approximation. "More proteins in genome
A than in genome B" is `B=0 AND A>=1 OR B=1 AND A>=2 OR ... OR B=K AND A>=K+1`, where K is
the smallest count for which `B>=K+1` returns no group; each term fixes B's count, AND
binds before OR as the site reads it, and `B=0` is the only form that matches a group with
no protein in B. FRAME builds it with `build_protein_count_comparison` (veupathdb-mcp),
which reads K from the site with count reports, and binds the expression whole; it never
writes the ladder by hand. What remains of this item is the comparison between clades.

## Change

1. The Lead's guidance for OrthoMCL names the pattern: a copy-number comparison between
   clades is built as count bands over each clade's genome list, and the answer states
   that it compares clade averages, not each genome.
2. The clarifying question offers that approximation with its numbers (the genome counts
   of each clade, the bands it would write) instead of asking for raw thresholds, and the
   turn builds it when the user agrees.
3. VERIFY judges the strategy against the approximation the user accepted, and states the
   remaining gap (average versus every genome) as a caveat, not a failure.
4. Approximation recipes for questions over higher taxonomic groups (a species
   with many strains, a genus, a phylum) are collected with the suggested-prompt
   candidates (card 43) and become guidance once a measured run passes.

## Measured on QA OrthoMCL (build 8.2)

The expression accepts protein counts with `>=` and `<` over a `+` list
(`tgon+tggt>=4 AND tgon+tggt<6` returns 494 groups). The parameter declares no length
limit: a four-band expression over the 61 Plasmodium and 15 Toxoplasma gondii codes
(2,842 characters) returns 51 groups, and a 4,264-character expression also runs. No
clade code names Plasmodium or Toxoplasma alone (`HAEM` holds 63 genomes, two of them
outside Plasmodium), so each clade is written as its list of genome codes.

## Done when

The example question builds a banded expression after one clarifying exchange, the answer
names the clade-average caveat, and a replay test covers the build.
