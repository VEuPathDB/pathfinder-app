---
type: Backlog
title: An ortholog in a genus means any of its genomes
description: Asked for genes with an ortholog in a genus, the Orthology Phylogenetic Profile binds every genome of the genus as required, so a gene with an ortholog in one of 61 Plasmodium genomes but not another is dropped.
tags: [orthology, phyletic, reading]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: proposed
---

# An ortholog in a genus means any of its genomes

## What I did

Asked on QA CryptoDB, on Luna: "Which Cryptosporidium genes have an ortholog in
Plasmodium but no ortholog in Toxoplasma?" The same shape ran on PlasmoDB,
ToxoDB, GiardiaDB, AmoebaDB, TriTrypDB, FungiDB and TrichDB.

## What I got

Strategy 214650150, one Orthology Phylogenetic Profile step, 501 genes, with
`included_species` set to all 61 Plasmodium genome codes (`padl, pbbi, pber, ...,
pyyx`): profile `%padl:Y%pbbi:Y%...`. Each code marked `Y` is required. VERIFY
passed with no check failing. On TriTrypDB, "orthologs in T. brucei, T. cruzi, and
Leishmania" required all 52 genomes of the three genera (3,768 genes); on
AmoebaDB, "an ortholog in Giardia" required all 8 Giardia genomes.

## Why that's wrong

"Has an ortholog in Plasmodium" means an ortholog in at least one Plasmodium
genome. Requiring all 61 drops every gene whose ortholog is missing from one
assembly, so the count in the reply is smaller than the answer and the reply does
not say a stricter reading was taken. The exclusion side (no ortholog in any
Toxoplasma genome) is read correctly.

## Why it happens

The phylogenetic-profile search states one flag per genome and has no "any of"
form; the build expands the genus into its genome codes and marks each `Y`.

## Fix

Not decided. An "any genome of a clade" requirement is a union of one profile step
per genome, or a phyletic expression on the group search followed by a transform
to genes; the card that chooses must measure both on QA.

## What you'd get

A count of Cryptosporidium genes with an ortholog in at least one Plasmodium
genome and none in Toxoplasma, larger than 501. The suggested questions now name
one genome per side, which has one reading.
