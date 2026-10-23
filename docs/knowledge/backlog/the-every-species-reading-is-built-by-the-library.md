---
type: Backlog
title: The every-species reading is built by the library
description: FRAME writes presence in every species of a group by hand, one unit per species from the parameter's help; veupathdb-mcp gains a builder that writes it from the site's taxonomy, and FRAME binds its expression whole.
tags: [frame, orthomcl, phyletic, veupathdb-mcp]
generated: { by: claude-code/opus-5.5, at: 2026-10-22T00:00:00Z }
status: proposed
---

# The every-species reading is built by the library

## What happens

The parameter's help states the every-species reading of a genome list as one unit
`S>=ceil(k/2)T` per species S of k genomes, joined with AND. FRAME writes those units
itself from the species `lookup_phyletic_codes` returns. A hand-written reading can drop a
second strain of a species or round a half the wrong way, and the site counts what was
written. PathFinder now refuses an expression that leaves out a genome of a taxon FRAME
states as whole, but it cannot check each unit's threshold.

## Change

veupathdb-mcp gains a tool beside `build_clade_only_expression` that takes a clade code or
a list of genome codes and returns the every-species expression written from the site's
taxonomy (one unit per `species_of` group, each at half its genomes rounded up), with the
groups it returns. PathFinder takes the release, gives FRAME the tool, and FRAME binds the
expression whole.

## Done when

The library release carries the tool, FRAME's toolset lists it, and a unit test on the
recorded taxonomy shows the built expression names every genome of the group with each
species at half its genomes rounded up.
