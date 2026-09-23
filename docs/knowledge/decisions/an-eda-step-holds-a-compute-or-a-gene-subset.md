---
type: Decision
title: An EDA step holds a compute or a gene subset
description: A step exports genes, so create_eda_step writes a subset export only when a filter names the study's gene entity (the one entity that carries VEUPATHDB_GENE_ID), a compute export only when the analysis holds a computation, and an effect_direction only with both thresholds on a computed analysis; an analysis with no filter and no computation has no eda_analysis_spec and never reaches the graph. Counting the gene entity under the subset was rejected, because on a gene-by-sample counts entity a sample filter leaves rows, not genes.
tags: [eda, export, strategy, agent]
generated: { by: claude-code/opus-5, at: 2026-09-23T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-23T00:00:00Z }
status: stable
---

# What was decided

**A step holds a compute or a gene subset.** The gene entity is the one entity
that carries `VEUPATHDB_GENE_ID` (`find_gene_entity`, `has_gene_id` in
`describe_eda_study`). In an RNA-Seq study that entity is the per-sample counts
entity, a child of the sample entity, so each of its rows is one gene in one
sample.

- A subset export (no thresholds) needs a filter on the gene entity.
  `services/eda/gene_subset.py::refuse_a_subset_that_selects_no_genes` refuses
  any other subset before a step exists with `NoGeneSubsetError` (422), whose
  detail states what the analysis holds (its filters by entity and its
  computations) and names `run_eda_compute` and `set_eda_filters`. With a
  computation already on the analysis it names the two thresholds instead. A
  gene subset that counts 0 genes is still refused. `create_eda_step` turns the
  refusal into a retry with the same sentence, and the tab's export
  (`export_analysis_step`) answers it as the 422 problem.
- A compute export (both thresholds) needs a computation; `eda_step_request`
  raises `NoComputationError`, which the tool turns into a retry that names
  `run_eda_compute`.
- `effect_direction` defaults to unset. A direction on an analysis with no
  computation, or without both thresholds, is refused
  (`refuse_a_direction_without_a_volcano`).
- `serialize_spec` raises `EmptyAnalysisError` for an analysis with no filter
  and no computation, so neither the tool nor the tab's export route can build
  a step whose `eda_analysis_spec` is empty. The push refusal in
  `services/strategies/_wdk_step_calls.py` stays as the last check.

**A preview says which entity it counted.** `preview_eda_subset` prints a gene
count only when a filter names the gene entity. Otherwise it states the count
as a count of the counted entity and says the subset does not filter genes.

# What was rejected

**Count the gene entity under the subset and refuse a zero.** A filter on the
sample entity restricts the counts entity to the rows of those samples, so the
count is not zero, and the preview reported it as a gene count: 535,832 of
1,266,512 rows under a 44-sample subset, while the exported step answered 0
genes on the site. The rule reads which entities the filters name, which needs
no count and cannot mistake rows for genes.
