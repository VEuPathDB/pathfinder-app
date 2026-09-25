---
type: Decision
title: A word of the criterion is held to the site's parameters
description: set_criterion reads each word of the criterion text against WDK's own definitions - the bound search, the searches the framing pass ranked or opened, and the parameter names of the record type's searches - so a search that cannot state a word another search of the pass states is refused, a parameter that can state it is held to a value that does, and a word no search of the pass states is recorded unmet, which the ledger blocks on, VERIFY cannot pass over and the reply names. A synteny-only rule, a word list, words the model declares and a similarity threshold were rejected.
tags: [frame, catalog, turn-contract, verification, orthology]
generated: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-09-25T00:00:00Z }
status: stable
---

# What was decided

**The evidence.** A cataloged thread asked plasmodb to keep only the genes with
syntenic orthologs in P. vivax P01. FRAME bound the Orthology Phylogenetic
Profile, which has no synteny parameter, and the word was dropped: the INTERSECT
kept 73 genes where the syntenic round trip keeps 67
([WDK-MAP-009](../wdk/pathfinder/rules/pathfinder-mapping.md)). Transform by
Orthology states it through "Syntenic Orthologs Only?".

**The rule reads the site, not a word.** `ai/tools/standalone/_frame_qualifiers.py`
runs on both `set_criterion` calls:

- A word of the criterion is a qualifier when it has at least four letters
  after a light stem, is not negated ("non-syntenic" states an absence), and
  exactly one search of the record type names a parameter by it
  (`_qualifier_words.py::the_one_search_naming`). On plasmodb's transcript
  searches "only" is carried by 197, "genes" by 24 and "with" by 7, which makes
  them shared vocabulary; "synten" and "pseudogen" by one each. A qualifier is
  held to a search, by a refusal or by a parameter value, only when the pass
  read the search that names it; the unmet check below uses the same one-search
  test and reads the whole listing. So "from" is not a qualifier of "genes from
  Plasmodium falciparum 3D7 with a predicted signal peptide": only Telomere
  Proximity's `distanceFromTelomere` names it, and no pass that binds a signal
  peptide read that search, so the Text search's "Fields" label that carries it
  does not refuse the bind. "plasmodium" names no parameter at all, so the
  pathway search whose Organism labels carry it does not refuse an RNA-Seq bind.
- A word the bound search's definition does not use (its names, help and every
  vocabulary label), that a visible parameter of another search the pass ranked
  or opened a sheet for states by its display name or by a label of a short
  vocabulary, refuses the bind and names that search and parameter. A transform
  maps the genes another criterion states, so a word the search of another
  criterion of the draft uses is that criterion's and not the transform's.
- A parameter of the bound search that can state the word is held to a value
  that does: never its default, never the option labelled "no". A word the
  search's own name or display name states asks for the search itself, not for
  one of its parameters (`_qualifier_words.py::named_stems`): "orthologs" binds
  Transform by Orthology at the site's synteny default, and only "syntenic"
  holds "Syntenic Orthologs Only?" to yes. On toxodb that is 145 Neospora
  genes where the parameter held to yes answered 69.
- A neighbouring search whose definition the site cannot answer is left out of
  the comparison, never raised: the bind names it in the trace ("not compared:
  ...") and in `SetCriterionResult.unreadSearches`. The bound search's own
  definition failing still refuses the call and names that search.
- A word no search of the pass states, and one search of the record type names a
  parameter by, is recorded on `Criterion.unexpressed_qualifiers`. The ledger
  grounds it as a user-explicit hard constraint that is `ungroundable`, VERIFY's
  success is held while it stands (`ai/lead/verify_dispatch.py`), and the turn
  contract's `unstated_qualifier` refuses once a reply that does not name it.

The second measured case is "pseudogenes": Gene Type states it through "Include
Pseudogenes", and its neighbour Organism cannot. Across the unit suite 139
existing tests run through the rule and none is refused by it.

# Rejected

- **A synteny rule.** It fits one word to one search pair, and the next dropped
  qualifier needs its own rule.
- **A list of qualifier words.** It goes stale as the sites add parameters, and it
  is PathFinder's vocabulary put in place of WDK's.
- **Words the model declares.** The measured miss is the model dropping the word,
  so a declaration the model writes checks nothing.
- **A similarity threshold between the text and a parameter.** A cosine cut picks
  a number, not a reason; the rule reads whether a parameter's own words carry
  the word, the way `SearchChoice` reads its basis
  ([a criterion says why its search was chosen](a-criterion-says-why-its-search-was-chosen.md)).
- **Reading every search of the site for the unmet check.** The site has 359
  transcript searches, and a definition read for each is a read per search on
  the first binding of a pass. The parameter names already in the catalog's
  listing say which words the site names a parameter by.

# What it does not cover

A word no search of the record type names a parameter by, and that no search of
the pass states in a label, is neither refused nor recorded: "curated" on a pass
that never read GO Term is such a word. A spec derived from the strategy alone
(`spec_from_ast`, for a thread that holds no spec) carries no
`unexpressed_qualifiers`, so a requirement recorded unmet does not survive that
derivation.
