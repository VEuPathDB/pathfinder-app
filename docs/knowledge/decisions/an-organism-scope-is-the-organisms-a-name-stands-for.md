---
type: Decision
title: An organism scope is the organisms a name stands for
description: The check that refuses an INTERSECT of two organism scopes and VERIFY's organism check both compare the organisms under each entry of the site's organism tree, so a taxon or a species entry stands for the organisms the tree holds under it and an organism entry stands only for itself. The refusal reads the tree only when two scopes differ by name. The scope of a combine reads both of its inputs. Comparing the names, a remedy that tells the pass to narrow the taxon, storing each criterion's organisms on the spec, and the primary input alone as the scope of a combine were rejected.
tags: [strategy, organism, validation, frame, commit]
generated: { by: claude-code/opus-5.5, at: 2026-10-12T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-11-12T00:00:00Z }
status: stable
---

# What was decided

**A scope is a set of organisms.** An organism parameter that WDK draws as a
tree takes a parent entry, such as a phylum, a genus or a species above its
strains, and runs the search on every organism under it.
`domain/strategy/organism_scope.py::SelectedOrganisms` holds the entries a
scope selects with `taxa` (`SiteTaxa`), the organisms under each entry that
holds some, and
is the only form an organism comparison takes: its organisms are the entries
with each parent entry replaced by the organisms under it.
`domain/strategy/validate.py::cross_organism_refusal` refuses an INTERSECT only
when the two sets share no organism. The refusal still names each scope by the
entry the search was given.

**VERIFY's organism check compares a record's organism with those organisms.**
`ai/lead/verify_checks.py::_organism_checks` reads `organism_taxa` for the
marked searches of the spec and hands `domain/site_checks.py::organism_check` a
`SelectedOrganisms`. A record organism is selected when its words equal the
words of one organism of the scope, so a clade admits every organism under it
and a strain does not admit a sibling strain whose name it begins. A requirement
carries the check when the scope selects every organism under its entry.

**The commit reads the site's tree when the names disagree.**
`services/strategies/organism_params.py::organism_taxa` reads the organism tree
of each search that marks an organism parameter
(`domain/strategy/named_taxa.py::organism_trees`), and `tree_taxa` reads it only
when an INTERSECT of the tree joins two scopes that differ by name, so a tree
whose scopes agree reads nothing more than before. Every reader of the check
passes it: the commit (`tree_cross_organism_refusal`), FRAME's `set_structure`
(`ai/tools/standalone/_frame_organisms.py`), the plan validation and the sync.
**An entry the site does not place is not compared.** When a marked search's
tree cannot be read, `organism_taxa` also reads the organisms the site lists
(`list_organisms`), and an entry that is neither a parent entry of a read tree
nor a listed organism is unplaced: it may be a clade whose organisms are not
known. VERIFY's organism check is then `unchecked` (`no_check`, so it never
blocks the verdict) and says the site's organism list could not be read, and the
refusal does not refuse an INTERSECT with an unplaced side. A selection of
listed organisms is still compared by name. With no tree to read, every name
stands for itself.

**The scope of a combine reads both of its inputs.**
`domain/strategy/organism_scope.py::output_organisms` is the client library's
`extract_output_organisms` with the dataset organisms of each search that marks
no organism parameter (`dataset_organisms_of`, keyed by step id). UNION and
INTERSECT take the organisms of both inputs and are unknown when one input is
unknown, MINUS and LONLY take the primary input, RMINUS and RONLY the secondary
input, and a colocation the input its output names
(`veupathdb-py: docs/knowledge/decisions/a-combine-scope-folds-both-inputs.md`).
No reader walks the primary input alone:

- VERIFY's organism check and the INTERSECT refusal compare that scope, so the
  verdict does not depend on which input is the primary one.
- The refusal's remedy names the searches whose datasets alone give a side its
  scope (`organism_remedy.py::_experiments`); a side where a parameter states
  some organism gets the general remedy.
- The organism fold names as carriers the criteria whose organisms the
  sibling's output holds (`spec_fold.py::_OrganismReading.carriers_of`): an
  input with the whole scope, else both inputs.
- The records-organism caveat compares the root's scope with the scope of the
  same tree with each transform replaced by its input
  (`orthology.py::organism_change`), so a UNION of two organisms changes no
  organism.

# What was rejected

**Comparing the names.** `Apicomplexa` and `Plasmodium knowlesi strain H` share
no name, and the portal's tree holds 139 organisms under `Apicomplexa`, that
strain among them. In 1,107 saved turns the check refused 14 times and each
pair was two different organisms. Seven refusals outside them compared a taxon
or a species entry with an organism: six of the seven pairs share an organism,
and each turn then took an orthology transform it did not need or ended at its
budget.

**A word prefix for VERIFY's check.** A record organism matched a selected
value whose words began its name. `Apicomplexa` begins no organism's name, so a
correct strategy scoped to the phylum failed the check, and
`Plasmodium chabaudi chabaudi` begins `Plasmodium chabaudi chabaudi CB`, so a
strain admitted its sibling.

**Failing or refusing an entry the site does not place.** Without the tree,
`Apicomplexa` is one name, so its own organisms would fail the check and its
INTERSECT with one of them would be refused.

**A remedy that narrows the taxon.** "Scope every seed to one organism" asks the
pass to change what the researcher asked for across the taxon.

**The organisms of each criterion stored on the spec.** A step the site or the
canvas adds has no such record, and the commit would read the tree for it anyway.

**The primary input alone as the scope of a combine.** An INTERSECT of a UNION
of four experiments on three organisms with an ortholog search on `Apicomplexa`
had the scope of the first experiment, so the check failed the records of the
other two organisms. With the inputs swapped, the scope was `Apicomplexa`, and
the check passed.

**The intersection of the expanded scopes of an INTERSECT.** An INTERSECT
returns only records that both inputs return, so a record's organism is in the
scope of each input. A check against the intersection fails no record that a
check against the union passes, and it needs the site's tree for every entry.

# Anchors

`domain/strategy/organism_scope.py::SelectedOrganisms`,
`domain/site_checks.py::organism_check`,
`ai/lead/verify_checks.py::_organism_checks`,
`domain/strategy/validate.py::cross_organism_refusal`,
`domain/strategy/organism_remedy.py`,
`services/strategies/organism_params.py::organism_taxa`,
`ai/tools/standalone/_frame_organisms.py`,
`tests/unit/domain/strategy/test_a_taxon_meets_the_organisms_under_it.py`,
`tests/unit/services/strategies/test_a_taxon_scope_is_read_from_the_sites_tree.py`,
`tests/unit/ai/tools/test_set_structure_reads_a_taxon_from_the_sites_tree.py`,
`tests/unit/ai/lead/test_a_clade_selects_its_organisms.py`,
`tests/unit/domain/strategy/test_a_combine_scope_reads_both_inputs.py`.
