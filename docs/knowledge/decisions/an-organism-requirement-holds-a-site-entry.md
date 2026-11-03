---
type: Decision
title: An organism requirement holds a site entry
description: An organism requirement's typed value is one entry of the site's organism list, compared by equality wherever an organism is compared. The gate binds the entry the researcher's message states whole, else the one a Decisions choice over the site's entries settles; otherwise the requirement holds no entry and the card asks which entry the researcher means. Binding the reading's words when they are an entry, keeping the word readings as the comparison, and refusing an ortholog organism the site's own list lacks were rejected.
tags: [requirements, verification, frame, decisions, organisms]
generated: { by: claude-code/opus-5.5, at: 2026-11-03T00:00:00Z }
status: stable
---

# What was decided

`OrganismValue` (`domain/strategy/constraints.py`) holds `organism`, one entry
of the site's organism list (`veupathdb_mcp.gene_lookup.list_organisms`, the
leaves of the organism vocabulary). The message reading writes the organism as
words (`StatedOrganism.organism` in `domain/message_reading.py`), and
`hold_the_intent` turns them into an entry before the thread records the
requirement (`ai/lead/organism_reader.py::named_organisms`):

1. The one entry the researcher's message states whole, its genus possibly an
   initial, that the words are or begin, binds
   (`domain/strategy/organism_phrases.py::completed_entry`). The words alone
   never bind: an entry the message does not state goes to step 2.
2. Else one Decisions choice over the site's entries (the 254 nearest the words
   on a site that lists more) and `none_fits` reads the researcher's message and
   the requirement's quote. A picked entry binds when the choice reaches
   `DECISIONS_VOCAB_MIN_CONFIDENCE`. The call goes through the installed Decisions
   transport, which meters it.
3. Else the requirement holds no value and the thread holds the pick
   (`ThreadRequirements.organism_picks`, an `OrganismPick` with the picked entry
   and the nearest entries). The next framing pass's card asks "Which organism of
   this site do you mean by ...?", one `SetOrganism` option per offered entry,
   the pick recommended, the note as the free-text route; the pass ends
   `needs_user` and no build runs until the question is answered. A picked
   option names the requirement's entry in place. A service that does not answer
   gives the same question over the nearest entries. The mock deployment asks no
   service, and its arcs write entries their prompts state.

The entry is compared by equality:

- grounding: a criterion whose organism parameter selects the entry realizes
  it; a criterion that links the requirement and holds a taxon pick realizes the
  taxon;
- the organism check: a requirement whose entry the strategy selects carries the
  result organism check, and one with no entry is `unchecked`;
- FRAME's bind refusal names the entries the live requirements hold
  (`match_exact_option`), and a requirement with no entry names none;
- the organism drop is met when the dropped criterion links only organism
  requirements, each with an entry;
- `gene_record`'s `ortholog_organism` reads the rows whose organism is that
  name; when none is, the answer names the nearest organisms the table holds.

# Why

The grounding, the check, the bind refusal and the drop read the model's value
with word prefixes (`stated_organisms`, `names_the_organism`) or the criterion's
text, and the gate rewrote the value by a word prefix (`complete_organisms`). A
value written another way grounded another way. An entry of the site's list is
data both sides hold, so equality decides.

On 49 labelled corpus turns that state organisms on sites with a recorded
organism list (51 requirements; 45 name one entry, 6 a genus, a species of
several strains or a family), two runs of the wired reading and this
validation on Luna resolved every requirement they extracted to the hand
label: 50 of 50 and 49 of 49, each run asking all 6 that name no single entry.
The reading left out one requirement in each run, a strain named in a
question, and the provider refused one message of the second run. 11 and 9
turns needed the Decisions step; 4 and 3 of them settled an entry the words
did not complete to, one over a reading that wrote another genus ("E. bieneusi
H348" read as Encephalitozoon, settled as Enterocytozoon bieneusi H348).

The choice alone settled all 51 of those requirements to the hand label. Over 14
misspelled names on nine sites it picked the right entry every time, and over 32
names that state no single entry it answered `none_fits` for 31; the other,
"Trypanosoma cruzi CL Brener", bound the site's entry for that strain.

# What was rejected

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

`tests/unit/ai/lead/test_an_organism_requirement_holds_a_site_entry.py` replays
the recorded Decisions exchanges (`tests/fixtures/decisions/organism_*.json`:
"3D7" settled at 0.99; "Plasmodium falciparium 3D7" settled at 0.95; "Plasmodium
falciparum" answered `none_fits` at 0.96) over the recorded PlasmoDB list, and holds the completion,
the settled entry, the card question, its answer, the unanswered service, the
mock deployment and the build hold.
`tests/unit/domain/strategy/test_an_organism_completes_to_an_entry_the_message_states.py`,
`test_an_organism_is_grounded_by_its_entry.py`,
`test_the_fold_drops_an_organism_universe.py`,
`tests/unit/ai/tools/test_the_organism_the_request_names_is_bound.py`,
`tests/unit/ai/lead/test_a_second_organism_fails_the_verdict.py` and
`tests/unit/services/gene_records/test_read_gene_record.py` hold each comparison.
