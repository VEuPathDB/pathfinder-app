---
type: Decision
title: An organism scope is the organisms a name stands for
description: The check that refuses an INTERSECT of two organism scopes compares the organisms under each entry of the site's organism tree, so a taxon or a species entry meets the organisms the tree holds under it. The tree is read only when two scopes differ by name. Comparing the names, a remedy that tells the pass to narrow the taxon, and storing each criterion's organisms on the spec were rejected.
tags: [strategy, organism, validation, frame, commit]
generated: { by: claude-code/opus-5.5, at: 2026-10-12T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-10-12T00:00:00Z }
status: stable
---

# What was decided

**A scope is a set of organisms.** An organism parameter that WDK draws as a
tree takes a parent entry, such as a phylum, a genus or a species above its
strains, and runs the search on every organism under it.
`domain/strategy/organism_scope.py::organisms_of` turns a scope into those
organisms through `taxa`, the organisms under each entry that holds some, and
`domain/strategy/validate.py::cross_organism_refusal` refuses an INTERSECT only
when the two sets share no organism. The refusal still names each scope by the
entry the search was given.

**The site's tree is read when the names disagree.**
`services/strategies/organism_params.py::organism_taxa` reads the organism tree
of each search that marks an organism parameter
(`domain/strategy/named_taxa.py::organism_trees`), and `tree_taxa` reads it only
when an INTERSECT of the tree joins two scopes that differ by name, so a tree
whose scopes agree reads nothing more than before. Every reader of the check
passes it: the commit (`tree_cross_organism_refusal`), FRAME's `set_structure`
(`ai/tools/standalone/_frame_organisms.py`), the plan validation and the sync.
A search the catalog cannot read gives no entry, and its names stand for
themselves.

# What was rejected

**Comparing the names.** `Apicomplexa` and `Plasmodium knowlesi strain H` share
no name, and the portal's tree holds 139 organisms under `Apicomplexa`, that
strain among them. In 1,107 saved turns the check refused 14 times and each
pair was two different organisms. Seven refusals outside them compared a taxon
or a species entry with an organism: six of the seven pairs share an organism,
and each turn then took an orthology transform it did not need or ended at its
budget.

**A remedy that narrows the taxon.** "Scope every seed to one organism" asks the
pass to change what the researcher asked for across the taxon.

**The organisms of each criterion stored on the spec.** A step the site or the
canvas adds has no such record, and the commit would read the tree for it anyway.

# Anchors

`domain/strategy/organism_scope.py::organisms_of`,
`domain/strategy/validate.py::cross_organism_refusal`,
`domain/strategy/organism_remedy.py`,
`services/strategies/organism_params.py::organism_taxa`,
`ai/tools/standalone/_frame_organisms.py`,
`tests/unit/domain/strategy/test_a_taxon_meets_the_organisms_under_it.py`,
`tests/unit/services/strategies/test_a_taxon_scope_is_read_from_the_sites_tree.py`,
`tests/unit/ai/tools/test_set_structure_reads_a_taxon_from_the_sites_tree.py`.
