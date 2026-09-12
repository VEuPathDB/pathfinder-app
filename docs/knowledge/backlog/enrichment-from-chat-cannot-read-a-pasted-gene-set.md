---
type: Backlog
---

# Enrichment from chat cannot read a pasted gene set

**What I did.** On plasmodb, on the rebuilt stack where the Lead carries the enrichment tool: "Run a GO enrichment on my gene set 'gametocyte secreted candidates v3' and summarize the top terms. Then export that gene set as CSV and give me the link." That set (`1a52f8ea-ec94-4dec-aeec-852d3a4fdd0d`, 155 genes) has `source = paste`: gene ids, no WDK step and no search.

**What I got.** The task failed: `geneset_enrichment` task `6cc9bc18-b76d-4487-9ad5-d143ba9e0eef`, error "Validation failed: Either step_id or search_name+parameters required". The same gene set enriches fine through the workbench panel (`POST /gene-sets/{id}/enrich` returned 46 significant GO biological-process terms over the same 155 genes).

**Why that's wrong.** One operation, two answers: the researcher's own set enriches from the workbench and fails from the chat, and the chat failure is a validation message about step ids, which names nothing the researcher can act on.

**Why it happens.** Two facades reach the same analysis and only one knows about a pasted set. `services/gene_sets/operations.py::GeneSetService.run_enrichment` (the HTTP route) builds a temporary WDK dataset from the gene ids when there is no step and no search (`build_enrichment_params_from_gene_ids`). `services/workbench/gene_sets.py::run_gene_set_enrichment`, which the durable job calls, delegates to `services/gene_sets/enrichment.py::run_enrichment_for_gene_set`, which passes `gene_set.wdk_step_id` and `gene_set.search_name` straight to `EnrichmentService.run_batch`.

**Fix.** The dataset-building step moves into `run_enrichment_for_gene_set`, the one function both facades call, so a pasted set enriches by either route and neither caller repeats the rule. Red first: `run_enrichment_for_gene_set` on a gene set with ids and no step calls `run_batch` with the temporary dataset's search and parameters; the HTTP route's own test keeps passing with the branch removed from `GeneSetService.run_enrichment`.

**What you'd get.** The chat request returns the same terms the workbench panel returns, for the set the researcher named.
