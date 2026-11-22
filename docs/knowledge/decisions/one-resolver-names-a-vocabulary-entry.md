---
type: Decision
title: One resolver names a vocabulary entry
description: A text binds a vocabulary entry only when one exact step names it; every other text is refused with the five entries one ranking (`rank_entries`) holds nearest, led by the entry a Decisions choice picks, and nothing binds on a guess. Five matchers that disagreed, the lexical reader alone, spelling alone, accepting a single candidate, and binding a Decisions choice at a floor were rejected.
tags: [vocabulary, parameters, frame, decisions, refusals]
generated: { by: claude-code/opus-5.5, at: 2026-11-22T00:00:00Z }
status: stable
---

# What was decided

A text stated for a vocabulary parameter names an entry by one exact step,
`veupathdb-py: src/veupathdb/domain/parameters/vocab_lookup.py::exact_entry`: the
entry whose term or label matches the text folded as every vocabulary text is
(`match_exact_option`, which also takes a leading accession exactly one entry
carries), or the one entry a numeric text equals. Every path that reads a stated
value calls it: FRAME, an edit, a variant, `count_search`, an Explore reading,
validation and the push (`entries_or_refusal`, through `param_dag._bound` in
veupathdb-mcp).

A text no entry matches exactly binds nothing. It is refused
(`VocabularyEntryError`) with candidates from one ranking,
`rank_entries`: the entries the lexical reader (`read_options`) keeps, then the
entries `difflib` spells nearest, each entry once. The refusal shows five
(`SHOWN_CANDIDATES`). Before it is raised to an agent, the candidates are ordered
by `veupathdb_mcp.catalog.ordered_refusal` (and `ordered_by_vocabulary`,
`ordered_phyletic_refusal`): one Decisions choice over the first 254 ranked
entries (`DECIDED_CANDIDATES`), under the researcher's message, picks the entry
the words name or `none_fits`; a picked entry leads the five, and the rest keep
the ranked order. The choice orders the candidates and never binds. A service
that does not answer leaves the ranked order.

One refusal asks at most five choices: only its first five faults are ordered,
and every later fault keeps the ranking. A served tool (`veupathdb-wdk-mcp` on
8100) passes no context and asks none, so no served path spends the deployment's
key ([Decisions spend is metered](decisions-spend-is-metered.md)).

# Why

The labelled set: 458 phrases over 25 recorded vocabularies (GO, EC, InterPro,
Hagai pathways, organism trees, the phyletic tree and others), seed 20261122,
398 of them not exact. Two labellers labelled each phrase blind to how it was
made; before adjudication they agreed on the kind (entry, ambiguous, none, any
of) for 97.2% and on the answer for 95.9%, and 24 were adjudicated. The gold
file and the dev and held-out split were frozen before any arm ran (sha256
`c831b3d631d78950782ebe9cfcc0d38205fc61ed3e67db8199dfeccc79c8a4a7` and
`da1ba90b2ddc5ad5fc6ee4bf079f22424c4132b5ee38467d302033df6ee19aff`), and the
floor of each arm was chosen on the dev half only. On the 229 held-out rows (197
not exact), on gpt-6-luna:

| arm | right | accuracy (Wilson 95%) | confidently wrong |
|---|---|---|---|
| refuse: rank order, never bind | 197 | 86.0% (80.9-89.9%) | 0 |
| choice: bind the Decisions pick at a floor | - | out on dev | at least 1 at every floor |
| choice_fit: bind the pick when a fit check also reaches 0.80 | 208 | 90.8% (86.4-93.9%) | 1 |
| refuse_plus: rank order led by the pick, never bind | 219 | 95.6% (92.1-97.6%) | 0 |

A row is right when the binding is the gold entry or, for a refusal, when the
gold entry is among the five shown. refuse_plus gets 22 held-out rows that rank
order alone misses (GO 7, EC 6, Hagai 3, InterPro 3, one each in three organism
lists) and loses none; the rule fixed before it was scored adopted it only if it
beat rank order by at least 2 points. Because it never binds, it is never
confidently wrong. The live pass and its repeat cost $0.153 (1.53 million input
tokens); 40 repeated rows agreed 40 of 40. A refusal costs one choice per
unclear phrase, about $0.0003, median 0.87 s.

# What was rejected

**Five matchers that disagreed on one text.** Before this, five rules judged a
vocabulary text: the folded exact match, the canonicalizer's strip-only match,
the phyletic reader's case fold, a `startswith` reader and the audit genome
reader. `Protein Coding`, `missense`, `glycolysis` and
`Plasmodium  falciparum 3D7` (two spaces) were taken on FRAME and refused on
validation; `falciparum 3D7` was an audit genome the Lead would not bind.
`P. falciparum 3D7` was resolved on FRAME and refused on an edit with a refusal
that named a TriTrypDB organism and a tool the execution agent does not hold.
Spelling suggestions offered `Cysteine proteinases` for
`serine/threonine protein kinase` and omitted 3D7 from the card for
`P. falciparum`.

**The lexical reader alone.** `read_options` keeps no entry for an
abbreviation: `Pf3D7`, `PbANKA` and `AgamP4` get no candidate, and spelling
puts the right entry first for each.

**Spelling alone.** `difflib` misses words it does not spell like:
`serine/threonine protein kinase` gets protein phosphatases and carriers, and
`rhoptry` gets dihydropteroate synthase, while the lexical reader names nine
serine/threonine kinases and `IPR009864 Rhoptry-associated protein`.

**Accepting a single candidate.** The lexical reader keeps exactly one entry,
`Synonymous`, for `non-synonymous`, and `Plasmodium malariae` for
`malaria parasite`; taking it binds the opposite class or the wrong species
with no refusal.

**Binding the Decisions choice.** The choice arm reaches no floor with no
confidently wrong row on the dev half (`proteolysis enzyme` settles to
`GO:0006508` proteolysis at 0.97, gold `GO:0008233` peptidase activity). The
fit-checked arm at 0.80 settles `Duffy binding like domain` to `IPR008602` on
the held-out half, where two entries share the label; a wrong binding changes a
count with no sign. The FRAME vocabulary pick, its card and the Decisions
vocabulary readers were deleted with it, and the decision that recorded the
pick card is gone.

# What would prove this wrong

A held-out phrase that refuse_plus shows without its gold entry where a binding
arm with no confidently wrong row binds it. Held by
`tests/unit/ai/tools/test_one_resolver_names_a_vocabulary_entry.py` (FRAME and
an edit refuse a spelling with the same candidates; a strain code is refused
with the entry it abbreviates),
`veupathdb-py: tests/unit/domain/parameters/test_one_ranking_names_the_candidates.py`
and
`veupathdb-mcp: tests/unit/catalog/test_a_refusal_leads_with_the_decided_entry.py`
(the pick leads, an unanswered choice keeps the ranking, at most five choices
per refusal).
