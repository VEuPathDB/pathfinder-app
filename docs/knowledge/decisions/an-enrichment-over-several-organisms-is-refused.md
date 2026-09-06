---
type: Decision
title: An enrichment over a result of several organisms is refused until a background is named
description: WDK's enrichment plugins test one organism's genes against that organism's genome and the analysis form defaults to the first organism its result holds. A 10-gene ToxoDB set spanning 7 organisms was therefore tested as 1 Eimeria falciformis gene and reported 0 significant terms over 10 genes analyzed. EnrichmentService now refuses a result whose organism vocabulary holds more than one entry when no BackgroundSource organism was given, and names every organism. Running against the form default, choosing the majority organism, and one run per organism were rejected.
tags: [wdk-alignment, enrichment, mcp, workbench, e2e]
generated: { by: claude-code/fable-5-1, at: 2026-09-05T00:00:00Z }
verified: { by: claude-code/fable-5-1, at: 2026-09-05T00:00:00Z }
status: stable
---

# What was measured

On toxodb.org, the gene search `invasion` (no organism filter, 10 results) answers
with genes of 7 organisms: Eimeria falciformis Bayer Haberkorn 1970, Eimeria
intestinalis P0_A24, Neospora caninum Liverpool, Neospora caninum Liverpool 2019,
Sarcocystis neurona SN3, Toxoplasma gondii ARI and Toxoplasma gondii ME49. A step
built from those ids has count 10, and its `go-enrichment` and `word-enrichment`
forms offer an `organism` parameter of type `single-pick-vocabulary` whose
vocabulary is exactly those 7 organisms and whose `initialDisplayValue` is the
first of them, `Eimeria falciformis Bayer Haberkorn 1970`. With the search
narrowed to `Toxoplasma gondii ME49`, the same forms offer a vocabulary of one.

`EnrichmentService` ran with the form default, so the workbench tested the one
Eimeria gene against the Eimeria genome and the enrichment panel read "0
significant terms" beside "10 genes analyzed", with no word about the six
organisms it had dropped. The journey e2e on ToxoDB stopped on that panel.

# What was decided

`veupathdb_mcp.wdk.enrichment.service.EnrichmentService._execute_analysis` reads
the `organism` vocabulary of the analysis form WDK returns for the step. When no
`BackgroundSource.organism` was given and that vocabulary holds more than one
entry, it raises `AmbiguousBackgroundError` (a `ValidationError`) naming the count
and every organism, and the analysis is not run. `_run_analyses_on_step` turns it
into the `EnrichmentResult.error` the panel already renders and into the batch's
`errors` list, so the stored-set path, the durable job and the served
`enrich_gene_ids` tool all report it the same way. A vocabulary of one, or a named
background, runs as before. The background is still an organism, as
[enrichment of a gene list runs WDK's plugin](enrichment-by-value-runs-the-wdk-plugin.md)
decided; this decision adds that it must be unambiguous.

The journey seed (`apps/web/e2e/fixtures/seed.ts`) narrows every site's gene
search to the organism the journey already declared for it, so its sets are one
organism and its enrichment assertion is real.

# Rejected

- **Running against the form default, as before.** WDK's own page makes the user
  choose from that vocabulary; running without a choice put a number next to a
  term that the researcher could not reproduce on the site.
- **Choosing the majority organism.** Silent, and wrong for a set that is 5 and 5.
- **One run per organism.** Five analysis lifecycles per organism per type; a set
  of 7 organisms is 35 WDK analyses for a question nobody asked.

# Reopen when

A caller can state the organism from the workbench (the panel has no organism
control; the agent-side `run_gene_set_enrichment` takes none). Then the refusal
becomes a prompt for that control instead of a message.
