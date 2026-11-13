---
type: Decision
title: A long expression reads by what it counts
description: A phyletic expression whose described reading passes 200 characters is read from its parsed terms and the taxonomy, folded to a species, a genus or a clade only where the terms cover that group, with a stepped comparison read as a comparison; Strategist computes this over the library's public names. Raising the limit, folding inside the library's describe, and checking the reply were rejected.
tags: [orthomcl, phyletic, facts, strategy]
generated: { by: claude-code/opus-5.5, at: 2026-11-03T00:00:00Z }
status: stable
---

# What was decided

`expression_handles.py::expression_reading` keeps `PhyleticExpression.describe` up to
200 characters. Past that, `expression_folds.py::condensed_reading` takes the first of
these that fits `READING_LIMIT`:

1. **A stepped comparison.** Every OR term bounds one set on both sides and sets a floor
   on another, and the bands and floors both rise. When the counts are consecutive and the
   offset is constant it reads as "at least 1 more protein in B than in A, while A holds 0
   to 111 proteins"; otherwise each band is listed with its floor.
2. **The fold.** Each unit names its genomes by the group they cover exactly: a tree clade,
   a genus (the first word of `species_of`) or a species. A list that covers none is
   listed, with "14 of the 15 genomes of" where it is part of a species. Units of one
   count that each cover one species fold to "in each of the 23 species of Plasmodium".
   Every number is the count the terms state, and "all of" is used only when the count is
   the size of the list.
3. **The shape with detail.** The first and last OR terms, or a tally of what the AND
   clauses require.
4. **The shape.** The codes, the terms, the clauses per term and the characters.

An upper bound reads with the site's floor of one ("1 to 17 of"), because a unit other than
absence holds only for a group with a protein of its codes.

A computed comparison's facts lead with `held_by`, a sentence of the groups each side alone
holds and both sides hold, largest first, with their shares. It is built from the typed
counts, and it is the first row the researcher and the Lead read.

# Rejected

- **Raising `READING_LIMIT`.** A 3,400 character list of genomes is true and nobody can
  check it against a reply. The limit is a bound; the 200 is what keeps the row readable.
- **Folding inside the library's `describe`.** `describe` is the literal reading the
  builder's own limit and the small expressions use, and the choice of what a facts row
  shows belongs to this product. The fold reads only the library's public names, so it
  needs no release.
- **Checking or rewriting the reply.** A check on the model's words would be a rule per
  failure. The row beside the reply is what lets a researcher catch a wrong sentence.

# What falsifies it

`tests/unit/domain/strategy/test_an_expression_states_what_it_counts.py`, which reads every
OrthoMCL corpus writing and checks readings against `holds_for`,
`tests/unit/domain/strategy/test_an_expression_reading_words_each_unit.py`,
`tests/unit/ai/lead/test_the_facts_state_what_an_expression_counts.py` and
`tests/unit/ai/lead/test_a_computed_comparison_reaches_the_facts.py`.
