---
type: Decision
title: Enrichment of a gene list runs WDK's plugin, and the background is an organism
description: A gene list given by value becomes a temporary WDK dataset and runs the same three step-analysis plugins the stored-set path runs. The in-process exact hypergeometric was rejected because the annotated background lives in the site database, and a caller-supplied background gene list was rejected because the plugin refuses any organism its own result does not contain.
tags: [wdk-alignment, enrichment, services, mcp]
generated: { by: claude-code/opus-5, at: 2026-08-24T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-24T00:00:00Z }
status: stable
---

# What was decided

`veupathdb_mcp/wdk/enrichment/gene_ids.py:enrich_gene_ids_by_value` takes genes by value, with no
stored gene set. It builds a temporary WDK dataset addressed by `GeneByLocusTag`,
and hands that search to `EnrichmentService`, which is the same path a stored
gene set takes. The background is a `BackgroundSource`, and its only field is an
organism, which reaches WDK as the enrichment form's `organism` parameter.

The result names, per analysis type, the two wire columns its terms were read
from, because a wrong column name yields an empty column rather than an error
(WDK-ANS-007, `veupathdb-py: docs/knowledge/wdk/rules/searches-and-answers.md`).

# Rejected: computing the over-representation in process

`services/enrichment/stats.py:hypergeometric_log_sf` is exact and already serves
`run_custom_enrichment`, so a second enrichment could have been written over it.
It would answer with a different background than the site's own pages.

The plugin's background is the site database.
[`GoEnrichmentPlugin.validateFilteredGoTerms`](https://github.com/VEuPathDB/ApiCommonWebsite/blob/830bb57fe07fc2e4dd37b6ea2e3baae0eaee5bee/Model/src/main/java/org/apidb/apicommon/model/stepanalysis/GoEnrichmentPlugin.java#L100-L130)
counts terms in `webready.GoTermSummary_p`, filtered by evidence category, by
ontology and by GO slim membership. PathFinder holds none of that, and an
approximation of it would put a number next to a term that the researcher can
read differently on the same site the same afternoon.

`run_custom_enrichment` keeps its in-process test, because its background is an
experiment PathFinder itself computed.

# Rejected: a background the caller supplies as a gene list

The plugins take one background lever, and it is the organism.
[`EnrichmentPluginUtil.validateOrganism`](https://github.com/VEuPathDB/ApiCommonWebsite/blob/830bb57fe07fc2e4dd37b6ea2e3baae0eaee5bee/Model/src/main/java/org/apidb/apicommon/model/stepanalysis/EnrichmentPluginUtil.java#L27-L34)
refuses an organism that
[the result does not contain](https://github.com/VEuPathDB/ApiCommonWebsite/blob/830bb57fe07fc2e4dd37b6ea2e3baae0eaee5bee/Model/src/main/java/org/apidb/apicommon/model/stepanalysis/EnrichmentPluginUtil.java#L116-L131),
and
[`getOrgSpecificIdSql`](https://github.com/VEuPathDB/ApiCommonWebsite/blob/830bb57fe07fc2e4dd37b6ea2e3baae0eaee5bee/Model/src/main/java/org/apidb/apicommon/model/stepanalysis/EnrichmentPluginUtil.java#L93-L102)
narrows the result to that organism before the test runs. A background gene list
would have to be discarded or approximated, and either one is a number nobody
can reproduce.

An unnamed organism keeps the value the analysis form offers when the form offers
one; a form offering several is refused
([decision](an-enrichment-over-several-organisms-is-refused.md)).

# Consequences

The call costs one dataset, one step, one strategy and one analysis lifecycle per
type, which is why the gene list is capped
(`MAX_ENRICHMENT_GENE_IDS`). WDK validates the organism, so PathFinder does not
re-check it against a vocabulary; a wrong one is a WDK rejection carrying the
organisms the result does hold.
