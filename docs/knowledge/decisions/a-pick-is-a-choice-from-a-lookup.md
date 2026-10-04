---
type: Decision
title: A pick is a choice from a lookup
description: A new entry on a typeahead multi-pick parameter binds only when a lookup of that parameter in the same framing pass matched it; the facts name the lookup, its phrasings, the entries taken of the entries matched, and each picked entry whose label holds no word of the concept. A free pick with a caveat was rejected.
tags: [frame, vocabulary, parameters, facts]
status: stable
---

# The choice

WDK draws a vocabulary it means to be searched as a type-ahead box (`displayType`
`typeAhead`). For each such `multi-pick-vocabulary` parameter,
`ai/tools/standalone/_frame_lookups.py::refuse_a_pick_no_lookup_read`, called by
`set_criterion`, refuses a new entry unless a `get_parameter_options(query=[...])` read
of that search and parameter in the same pass matched it. The read records its matches
on `AgentToolState.looked_up`, keyed by search and parameter, as the union of the
`VocabLookup.matches` values of every lookup of it (`record_lookup`). With no lookup the
refusal names the lookup call to make; with a lookup it names the entries the lookup
matched. An entry the criterion already binds, and one the researcher's message writes
out as a whole token, is no new pick.

When a lookup term matched an entry whose label is that term, the pick for the entries
that term matched is that entry alone (`_refuse_a_pick_beside_the_exact_term`): another
entry the same term matched is refused unless a request message writes its label term
out, because a narrower entry beside the exact one states a different question and adds
nothing to the count (for "glycosome", GO:0020015 with three narrower GO terms counted
115 genes, as GO:0020015 alone does). An entry a different lookup term matched is
another concept and is not checked against this one. A new pick whose label shares no
uncommon content word with the request messages is refused unless a request message
writes its label term out (`_refuse_a_pick_off_the_request_words`), where a word more
than a tenth of the vocabulary's labels hold is common and a vocabulary of fewer than ten
labels holds none, so PF03392 ("Insect pheromone-binding family, A10/OS-D"), which
shares only "binding" with "odorant-binding protein", is refused.

`services/strategies/cut_picks.py::read_picks` records, for a pick from a lookup, the
lookup's phrasings and how many of its matches the pick took (`picked_from_a_lookup`,
"took 1 of the 2 entries that match 'odorant binding', 'OBP', 'PBP/GOBP'"), or how many
of the entries a cut list could not show (`picked_from_a_cut_list`), and each picked
entry whose label holds no word of any phrasing (`label_without_the_concept`).
`domain/value_caveats.py::LabelGapCaveat` shows each such entry as a caveat of the facts
part. A read that lists no entry counts no pick (`OptionsRead.taken`): a tree read,
such as an organism tree narrowed to "Cryptosporidium", returns its entries as a tree
and no list, so a count against it would read "took 0 of the 0 entries".
`get_parameter_options` writes a trace line for each kind of answer: a parameter
whose parents are unbound "needs <parents> first", which is not "not on the search".

# What was measured

The vectorbase Aedes aegypti LVP_AGWG Pfam vocabulary of `GenesByInterproDomain`
holds 8,027 entries, and the sheet shows the first 200 ranked by name. For
"odorant-binding protein genes on chromosome 3", a pick from that list took PF03392
("Insect pheromone-binding family, A10/OS-D"). A lookup of "odorant binding", "OBP" and
"PBP/GOBP" matches PF01395 ("PBP/GOBP family"), which gives 76 genes, 39 of them on
chromosome 3. On fungidb, a lookup of "lipase" matched GO:0007200 "phospholipase
C-activating G protein-coupled receptor signaling pathway", a label that holds no word
of the concept.

# What was rejected

**A free pick with a caveat.** The pick binds whatever the model took from the sheet,
and the facts add a caveat that it came from a list ranked by name. The count is then
the count of the wrong family, the caveat asks the researcher to find that out, and
every later turn builds on the wrong step. A refusal costs one lookup and the bound
entry is one the concept matched.

**A lookup required with any entry allowed after it.** The model may still bind an
entry from the ranked list once any lookup ran, so the lookup proves nothing about the
entry bound.
