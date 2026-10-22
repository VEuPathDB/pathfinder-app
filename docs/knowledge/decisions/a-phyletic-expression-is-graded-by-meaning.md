---
type: Decision
title: A phyletic expression is graded by meaning
description: An eval case states the accepted writings of each search's phyletic expression, and the scorer compares a produced expression to them through a normal form read as the site reads it, against the taxonomy the run read. Exact string comparison and the root count alone were rejected.
tags: [evals, orthomcl, testing]
generated: { by: claude-code/opus-5, at: 2026-10-21T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-10-21T00:00:00Z }
status: stable
---

# What a case states

`ExpectedOutcome.expressions` maps a search name to the writings a case accepts. Every
produced step of that search must carry a `phyletic_expression` whose meaning equals the
meaning of one accepted writing. A writing the grammar refuses, an unset value and a missing
step are each a difference, never an error. A case that states expressions and runs without a
taxonomy gets one difference, because no meaning can be read without it.

# The normal form

`pathfinder.evals.expressions` reads an expression as the site runs it: the site drops
parentheses and reads AND before OR, so the scorer does the same before it parses each
product. Each unit becomes a genome set, a kind (genomes or proteins) and an interval:

- A clade is the set of genomes under it, so a clade and its genome list are one unit.
- `>` and `<` become `>=` and `<=` on the next whole number. A genome count is clamped to the
  length of its list.
- Absence written `=0T` or `=0` is one unit. It is the only unit the site evaluates over every
  group; every other unit counts only groups with a protein in the list, so each of them also
  states presence. `L<=0T`, `L<0T`, `L<=0` and `L<1` are therefore never absence, and
  `L<=NT` over a list of N genomes is presence.
- Under AND, absence over a list and presence in every genome of a list both become one unit per
  genome, so a list writing and a one-genome-at-a-time writing grade equal. Single copy over a
  set of N genomes (every genome present and at most N proteins) becomes one `g=1` unit per
  genome. Units on one set intersect, and a presence unit implied by another unit on the same
  genomes or a subset of them is dropped.
- AND and OR terms compare as sets, so term and unit order do not matter.

The verdict (`drift.classify`) and the runner's summary both receive the taxonomy the run read
from the site at its start.

# Rejected

**Exact strings.** One meaning has many writings: a clade or its genome list, units in any
order, a sum of products with or without parentheses around each product. An exact match
fails every one of them, and the model is not wrong to choose another.

**The root count alone.** Two meanings can return close counts on one build and diverge on the
next, and a count says nothing about which reading was built. The count stays a separate
check, judged for drift against the site build.

# A run graded after its database is gone

`pathfinder.evals.run_directory.observed_from_run_directory` builds the same observation from a
chat-debugger run directory captured with its WDK exchanges. The turns are the `turn-<n>`
directories in numeric order, each followed by its `answer-<k>` directories, and an answer's
reply replaces its turn's. The strategy is the last strategy read across them, the gate is the
last one, and the last check's verdict stands only while the final strategy read has the steps,
parameters and tree of the read in the directory that holds that check. A temporary database
used for a run is removed when the run ends, so the run directory is what remains to grade.
`score_run_directory` refuses a case that states what no run directory holds (step reasons,
requirement rows, records shown, kept step ids, assumed values), and it takes the site build so a
root count off the recorded one is a difference, as `count_difference` reports it for a run read
from the database.
