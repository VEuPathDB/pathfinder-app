---
type: Decision
title: An organism requirement holds a site entry
description: An organism requirement's typed value is one entry of the site's organism list, compared by equality wherever an organism is compared. The gate binds the entry the researcher's message states whole or the one the words name exactly; otherwise the requirement holds no entry and the card asks which entry the researcher means, over ranked entries a Decisions choice may lead but never binds. Settling a Decisions choice at a floor, binding the reading's words when they are an entry, keeping the word readings as the comparison, and refusing an ortholog organism the site's own list lacks were rejected.
tags: [requirements, verification, frame, decisions, organisms]
generated: { by: claude-code/opus-5.5, at: 2026-11-03T00:00:00Z }
status: stable
---

# What was decided

`OrganismValue` (`domain/strategy/constraints.py`) holds `organism`, one entry
of the site's organism list (`veupathdb_mcp.catalog.list_organisms`, the
leaves of the marked organism parameter of `SequencesByTaxon`). The message reading writes the organism as
words (`StatedOrganism.organism` in `domain/message_reading.py`), and
`hold_the_intent` turns them into an entry before the thread records the
requirement (`ai/lead/organism_reader.py::named_organisms`):

1. The one entry the researcher's message states whole, its genus possibly an
   initial, that the words are or begin, binds
   (`domain/strategy/organism_phrases.py::completed_entry`). The words alone
   never bind: an entry the message does not state goes to step 2.
2. Else the entry the words name exactly, folded as every vocabulary text is
   (`veupathdb.domain.parameters.exact_entry`), binds.
3. Else the requirement holds no value and the thread holds the pick
   (`ThreadRequirements.organism_picks`, an `OrganismPick` with the offered
   entries): the five entries `rank_entries` ranks nearest the words, led by the
   entry one Decisions choice over the site's entries picks under the
   researcher's message (`veupathdb_mcp.catalog.ordered_by_vocabulary`). The
   choice orders the offer and never binds; a service that does not answer leaves
   the ranked order. The next framing pass's card asks "Which organism of this
   site do you mean by ...?", one `SetOrganism` option per offered entry, the
   note as the free-text route; the pass ends `needs_user` and no build runs
   until the question is answered. A picked option names the requirement's entry
   in place. A plan the researcher picks names an open requirement only when the
   words name one of the plan's organisms exactly. The mock deployment installs a
   transport that answers no choice.

The entry is compared by equality:

- grounding: a criterion whose organism parameter selects the entry realizes
  it; a criterion that links the requirement and holds a taxon pick realizes the
  taxon;
- the organism check: a requirement whose organisms the strategy selects, by
  the entry itself or under an entry of the organism tree, carries the result
  organism check, and one with no entry is `unchecked`;
- FRAME's bind refusal names the entries the live requirements hold
  (`match_exact_option`), and a requirement with no entry names none;
- the organism fold drops a leaf only when its count equals its organisms'
  gene count, so a criterion that links only organism requirements and counts
  fewer genes narrows and stays;
- `gene_record`'s `ortholog_organism` reads the rows whose organism is that
  name; when none is, the answer names the organisms the table holds nearest
  it, led by the one a Decisions choice picks under the turn's words.

# Why

The grounding, the check, the bind refusal and the drop read the model's value
with word prefixes (`stated_organisms`, `names_the_organism`) or the criterion's
text, and the gate rewrote the value by a word prefix (`complete_organisms`). A
value written another way grounded another way. An entry of the site's list is
data both sides hold, so equality decides.

A Decisions choice that settles an entry binds on a guess. On the 229 held-out
rows of the frozen vocabulary set (2026-11-22), binding the choice at a 0.80
floor read 208 right with one confidently wrong binding; refusing every
inexact text with the choice's pick first among the offered entries read 219
right (95.6%, 92.1 to 97.6) with none wrong, because it never binds. Plain rank
order read 197.

# What was rejected

**Binding the entry a Decisions choice settles at or above a floor.** It is the one
route that binds an entry the researcher did not state, and the held-out rows
above hold a confidently wrong binding under it. The organism reader's choice,
its floor and the vocabulary pick card are deleted.

**A fit predicate after the choice, the lower of the two reaching the floor.**
Over the same names it refused no wrong entry, and it refused 7 of the 14 misspelled
names the choice had right (fit 0.09 to 0.42 with choice 0.79 to 1.0). Saying in its
text that spelling does not matter, over 11 of those names, raised 2 and left 5 below
the floor.

**Binding the reading's words when they are an entry.** The words are a model's
reading of the message, and an entry the message does not state, such as a
strain written out for a species, would bind with no check against the
researcher's words.

**Keeping the word readings as the comparison where no value is held.** A
requirement the words decide is exactly one the type did not settle; it is
shown not verified instead.

**Refusing an ortholog organism the site's organism list lacks.** The rows of a
gene's ortholog table name the organisms of its ortholog group, which need not
be the site's own, so the table is the list the name is compared with.

# What would prove this wrong

`tests/unit/ai/lead/test_an_organism_requirement_holds_a_site_entry.py` reads the
recorded PlasmoDB list (64 entries) and holds the completion, a folded exact
entry, the card led by the choice's pick with nothing bound ("malaria", the pick
Plasmodium falciparum 3D7 first), the ranked entries when the service does not
answer ("P. falciparum" and "3D7" lead with Plasmodium falciparum 3D7, "malaria"
with Plasmodium malariae UG01), the card's answer and the build hold.
`tests/unit/ai/lead/test_a_picked_plan_names_the_organism.py` holds the plan's
exact naming and a species left to the card.
`tests/unit/domain/strategy/test_an_organism_completes_to_an_entry_the_message_states.py`,
`test_an_organism_is_grounded_by_its_entry.py`,
`test_the_fold_drops_an_organism_universe.py`,
`tests/unit/ai/tools/test_the_organism_the_request_names_is_bound.py`,
`tests/unit/ai/lead/test_a_second_organism_fails_the_verdict.py` and
`tests/unit/services/gene_records/test_read_gene_record.py` hold each comparison.
