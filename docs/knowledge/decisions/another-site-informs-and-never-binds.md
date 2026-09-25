---
type: Decision
title: Another site's experiment informs a criterion and never binds
description: search_for_searches answers the own site's searches exactly as before and appends one otherSites entry with up to three experiments from other VEuPathDB sites, each labelled with its site. None of them is a catalog hit, so none is a set_criterion candidate; a value one of them carries is refused with the three routes that are legitimate. read_experiment reads one card and records its record URL and PMIDs as retrieved, so FRAME may cite it. Rejected - one index over every site, binding another site's search, composing the lanes inside the tool server, and indexing other sites' searches instead of their datasets.
tags: [agents, catalog, frame, cross-site]
generated: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
status: stable
---

# What was decided

A strategy lives in one site's WDK. The researcher asked for the rule in these
words: rank the current site as it is, add a few from other sites for
diversity, and make the model know that those are not its own and stay in its
lane. The code holds that rule in four places.

**The own-site lane is untouched.** `veupathdb_mcp.catalog.search_for_searches`
is not edited, and `ai/tools/standalone/catalog.py::search_for_searches` builds
its list, the universal searches and the closeness note exactly as before. The
other-site lane is composed after it by a pure function,
`ai/tools/standalone/_catalog_elsewhere.py::with_other_sites`, so the own-site
entries are the answer's prefix entry for entry.

**The other-site lane is one trailing entry.** The tool server ranks the dataset
records of every other component site (`rank_experiments_elsewhere`: cosine
only, at most one card per site, three sites, nothing under the semantic
floor, nothing from the portal). PathFinder appends them as

```json
{"otherSites": {
  "note": "Experiments on other VEuPathDB sites. None can be bound on plasmodb. Read one with read_experiment to name a condition, a stage or an organism in a search on plasmodb.",
  "experiments": [{"site": "cryptodb", "datasetId": "DS_63b0de882c", "similarity": 0.52,
    "line": "cryptodb | Cryptosporidium parvum Iowa II | RNASeq | Transcriptome of 48 hours in vitro infection (Isaza et al.)"}]}}
```

A dataset shown once in a FRAME pass (`AgentToolState.elsewhere`) is not shown
again by a later call of the pass. An index that does not answer omits the
entry and changes nothing else.

**Binding is impossible by construction, and the refusal says why.** The
other-site entries never enter `CatalogRead.hits`, so they are never in the
`set_criterion` enum and never a read that `rationale_for` accepts.
`ValidatingEnumToolset` takes an optional `explain` hook, consulted before the
generic "is not a known value" retry. FRAME's hook,
`another_sites_entry`, matches the value against the shown entries' dataset ids
and searches and answers:

> GenesByRNASeqcparIowaII_Isaza_Infection_Time_Series_ebi_rnaSeq_RSRCPercentile
> is a search on cryptodb, and this strategy runs on plasmodb. An experiment on
> another site informs a criterion and is never bound: take its condition or
> stage into search_for_searches on plasmodb, cite it in why.sources, or carry
> its genes by orthology on the VEuPathDB portal, where one strategy holds both
> organisms. Nothing was recorded.

**An entry informs with provenance.** `read_experiment(dataset_id)` reads a card
the pass showed (the site comes from the shown entry, so the model cannot name
the wrong one) and answers its name, organism, assay, attribution, summary,
PMIDs, record URL, the first six searches it feeds with "These searches run on
cryptodb, not on plasmodb.", and what this site's orthology transform reaches.
It records the record URL and each PMID with
`TurnMarkers.record_retrieved_source`, so a `why.sources` that cites them passes
`_frame_rationale._retrieved`. It is read-only and capped at 6 calls a run.

**A study says which sites publish it.** `StudyCard.sites` is read with the
tool server's `sites_publishing` in one call per answer: the component sites
whose dataset records hold the study's dataset id, `["portal"]` when none does,
and empty when the store does not answer. The study search tool and the picker
row carry it; the picker draws it beside the source type.

**An organism only another site holds opens a new portal conversation.** A
conversation is bound to its site, so no card and no reply offers a site
switch. When a transform's organism value is on no entry of its sheet and
`sites_holding_organism` names another site, the unmatched-value retry adds
what the transform reaches here and the sentence "This needs the VEuPathDB
Portal, where one strategy holds both organisms. Open a new conversation there;
this conversation stays on <Site>." with the link `/veupathdb/conversation`
(`_frame_proposals.py::portal_only_sentence`). The retry records the sentence
on the pass (`AgentToolState.portal_route`); a pass that then changed nothing
answers the Lead with the sentence alone and no question
(`frame_dispatch.py::_accepted`), and one that changed something carries it
ahead of its summary. The Lead gives it word for word.

# Why the orthology sentence names the portal

The transform's organism sheet on each component site holds that site's own
clades only, measured with the service token on 2026-09-24:

| site | top of `GenesByOrthologs.organism` | leaves |
|---|---|---|
| plasmodb | Haemoproteidae, Plasmodiidae | 63 |
| toxodb | Eimeriidae, Sarcocystidae | 38 |
| cryptodb | Apicomplexa, Chromeraceae, Vitrellaceae | 23 |
| hostdb | Aves, Mammalia | 11 |

So another site's organism is not reachable by a transform here, and the card
says what the sheet reaches (read from the sheet, never written down) and that
a transform to the card's organism runs on the portal.

# Rejected

- **One index over every site.** The own-site ranking would change with every
  other site's catalog, which breaks the lane rule by construction. The portal
  repeats every component site's searches, so each would rank twice, and search
  names repeat across sites (`GenesByOrthologs` exists on every genomics site).
  A merged ranking hands FRAME another site's search as if it were bindable.
- **Letting FRAME bind another site's search.** A WDK step lives in one site's
  instance; a plasmodb strategy cannot hold a cryptodb step, and gene ids of two
  genera never meet under INTERSECT (`domain/strategy/validate.py`
  `cross_organism_refusal` refuses that combine, at `set_structure` before
  anything reaches WDK). The build would fail or answer nothing.
- **Composing the two lanes inside the tool server's `search_for_searches`.**
  Every host would get a changed own-site answer. The lane is the host's
  presentation, so the tool server serves two functions and PathFinder composes
  them.
- **Indexing other sites' searches instead of their datasets.** A search is the
  thing that cannot be bound; the dataset record carries the organism, the
  assay, the condition, the attribution and the publications.
- **Offering a site switch for a portal-only request.** No tool moves a
  conversation to another site, so a yes on such a card lands nowhere: on
  plasmodb it looped, asking the researcher to confirm the switch again.
- **An enum over the shown dataset ids for `read_experiment`.** The toolset's
  enum guard constrains nothing while its set is empty, so the tool checks the
  shown ids itself, and one check is enough.
