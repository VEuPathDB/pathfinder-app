---
type: Decision
title: An EDA step holds a compute or a gene subset
description: A step exports genes, so a subset export (the agent's or the tab's) needs a study with one gene entity (the entity that carries VEUPATHDB_GENE_ID) and a filter on it that selects at least one distinct gene id; a compute export needs a comparison, the analysis's first complete differential expression, and an effect_direction needs both thresholds on a compared analysis; an analysis with no filter and no computation has no eda_analysis_spec and never reaches the graph. A subset's range cut is exported only when a researcher message states its bounds, a card answer picked them, or a picked tail rule gives them on that study; the card that asks is built by code from the study's own distributions; a set filter rests on the study's own class, and the pinned filter sheet carries the study's own description. A gene count is the distinct gene ids under the subset, never the gene entity's rows. Counting rows of the gene entity was rejected, because on a gene-by-sample counts entity a row is one gene in one sample. A top-N cut on a rank or a score that no one stated was rejected, because it reads a property the study does not define; so were options the model writes and a cutoff parsed from a study's description.
tags: [eda, export, strategy, agent]
generated: { by: claude-code/opus-5, at: 2026-09-23T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-11-12T00:00:00Z }
status: stable
---

# What was decided

**A step holds a compute or a gene subset.** The gene entity is the one entity
that carries `VEUPATHDB_GENE_ID` (`find_gene_entity`, `has_gene_id` in
`describe_eda_study`). In an RNA-Seq study that entity is the per-sample counts
entity, a child of the sample entity, so each of its rows is one gene in one
sample.

- A subset export (no thresholds) needs a study with one gene entity and a
  filter on it. `services/eda/gene_subset.py::refuse_a_subset_that_selects_no_genes`
  refuses any other subset before a step exists with `NoGeneSubsetError`
  (422): a study with no gene entity, a subset whose filters name no gene
  entity (the refusal states the filters by entity and the comparisons, and
  with a comparison on the analysis it names the volcano cut instead), and a
  gene subset that selects 0 distinct gene ids. The error carries two
  sentences from the same facts: `detail` for the researcher, with no tool
  name and no id, and `retry` for the model, which names `run_eda_compute`,
  `set_eda_filters` or the two thresholds and the gene entity's id.
  `create_eda_step` raises the retry; the tab's export (`export_analysis_step`)
  answers the detail as the 422 problem.
- The tab offers the export for both kinds. "Export as step" sends the cut the
  figure was drawn at, which is the cut the analysis stores, once the figure of
  its comparison is read, and `thresholds: null` for an analysis that holds a
  filter and no figure; a refused subset shows the 422 detail under the button.
  The tab edits neither the subset nor the comparison
  ([PathFinder shows what the AI did](pathfinder-shows-what-the-ai-did-and-the-site-edits.md)).
- The analysis's comparison is its first complete differential expression
  (`differential_expression_computations`). An analysis the site's own EDA app
  edited also holds a `pass` compute for each plain plot, and can hold a
  differential expression the app has not finished; neither is a comparison.
  `run_eda_compute` replaces the comparison, or appends one, and keep every other computation as the site stored it
  (`services/eda/comparison.py`).
- A compute export (both thresholds) needs a comparison; `eda_step_request`
  raises `NoComputationError`, which the tool turns into a retry that names
  `run_eda_compute`. The exported document lists the comparison first with one
  volcano at the cut, then every other computation. The compute plugin takes
  the first computation holding a volcano with both thresholds and reads the
  cut from that computation's first visualization, so the comparison first,
  with the volcano as its only visualization, is the cut the plugin applies. A
  subset export keeps the site's order; its plugin reads the subset alone.
- A step's document is read back as what it selects by
  `services/eda/export.py::exported_analysis`, which reads it as the plugin
  of the step's stored analysis kind does: WDK picks the plugin by the
  search's query, the export stores the kind it writes and the catalog
  supplies it for any other step, so a `compute` step binds the first
  computation that holds a volcano and that computation's cut, and a `subset`
  step binds its subset and no cut, whatever volcano the document stores.
  The criterion the export is states that binding
  ([an EDA analysis is a criterion of the spec](an-eda-analysis-is-a-criterion-of-the-spec.md)).
- `effect_direction` defaults to unset. A direction on an analysis with no
  comparison, or without both thresholds, is refused
  (`refuse_a_direction_without_a_volcano`).
- A subset's range cut is stated or asked. Before anything is planned,
  `ai/tools/standalone/_eda_step_guard.py::subset_basis` reads each filter of
  the analysis against the study's sheet. A `numberRange` or `dateRange` bound
  at or past the variable's own end is open; every other bound must be stated
  by a researcher message or by a label the researcher picked on a card, read
  with the same `value_source` and `stated_words` that a search parameter is
  read with (`domain.card_picks` holds every picked label). Otherwise
  `create_eda_step` writes nothing and the guard builds the card itself
  (`services/eda/cut_offer.py`, `domain/eda_cut.py`), recorded in
  `domain.open_questions`, which `consult_user` asks as recorded. The Lead
  reaches the same card before it writes any filter with `ask_eda_cut`
  (`ai/tools/standalone/eda_cut.py`), which takes the variable of the open
  analysis: a model does not send a filter whose bound it was not told, so a
  card raised only by a refused export is never reached. With a tail rule held,
  `ask_eda_cut` returns that study's edge for the rule instead of a card. The options
  come from structured EDA data only, each distribution read with no filter
  through `preview_subset`, so each count is the study's own:
  - one option per class of each `stringSet` variable of the cut's entity with
    1 to 8 values, counted from its categorical histogram;
  - on a numeric cut, the lowest and the highest 5% and 10% of the variable.
    Each tail ends at the first bin edge where the cumulative count reaches the
    share. The label states the bound, then the count the bound's own range
    filter selects, read with one more `preview_subset` and never summed from
    the bins: a bin leaves out its upper edge and a range filter keeps its
    bound, so the two differ for every value on the edge. The filter's open
    end is the variable's declared range, since the outer bins can reach past
    it and the service refuses a bound outside that range. The share is that
    count over the records with a value. Counts are in genes on the gene entity and else in the entity's plural, for
    example `Lowest 6.5% of Mean Phenotype Score: at most -3 (65 genes)`. No
    edge is interpolated. A tail that holds every record is no cut, and a tail
    whose edge another share already reached is offered once. Both ends are
    offered, since code cannot know which end the researcher means.

  Tails come first and the card holds 8 options at most. A picked tail label
  states its bound, so it binds as a card pick, and its `PickTail` binding
  holds the rule and the variable's display name (`domain.tail_picks`, under
  the picked label). On a later study an unstated range cut of a variable with
  the same display name is accepted when its bound equals that study's own
  edge for the rule, computed the same way; any other bound is refused with a
  retry that names the study's edge, and no second card is asked. A variable
  of another name gets its own card: the end that means the same thing can
  differ between two variables, for example a fitness score and a rank of it. A pick that names no
  variable binds no variable. A picked class is that study's own value and binds as a
  set filter; it holds no rule, because vocabularies differ across studies.
  With no option to offer, the retry asks for the cut in the researcher's
  words. A
  set filter rests on the study's own class. The basis of each filter rides
  the binding (`AnalysisBinding.subset_basis`), and the facts part states it as
  the step's reason; a subset whose every filter is stated or picked takes
  that source. `set_eda_filters` pins the study's description from the catalog
  row beside the sheet, because a study defines its classes there (P. knowlesi
  A1H1 calls a gene with no CDS insertion `nonmutable` and essential).
- `serialize_spec` raises `EmptyAnalysisError` for an analysis with no filter
  and no computation, so neither the tool nor the tab's export route can build
  a step whose `eda_analysis_spec` is empty. The push refusal in
  `services/strategies/_wdk_step_calls.py` stays as the last check.

**A gene count is distinct gene ids.** `gene_count` reads the distribution of
`VEUPATHDB_GENE_ID` on the gene entity under the subset and under none, and
takes `numDistinctValues` from each. On the RNA-Seq study `DS_e973eadd57` the
counts entity holds 68,640 rows, 12 samples of 5,720 genes; a filter of at
least 1000 sense reads keeps 5,114 rows and 842 genes. On the phenotype study
the berghei subset keeps 4,011 rows and 5,595 of 5,803 genes, because one row
names several genes. The refusal's denominator and the preview's gene sentence
are this count, and the preview states it beside a count of the gene entity
too, since that count is rows. A preview whose filters name no gene entity
states the count of the counted entity and says the subset does not filter
genes. The step's own count is WDK's, once it runs. The two reads run in one
task group: a read the service refuses cancels the other, and the caller gets
the service's own error, not the group, so the refusal it words for the
researcher is the one it would word for a single read.

# What was rejected

**Let the agent pick a top-N cut on a rank or a score.** A request stated only
as a property ("essential in any experiment") gave four studies a `Rank 1..100`
cut each: 100 genes per study whatever the study measured, while the one study
that defines essential (`Mutability in CDS = nonmutable`) holds 2,009 such
genes. A cut is a question when neither the researcher's words nor the study's
own class settles it. Never asking the researcher, which the route block once
said, still holds for the analysis document only.

**Let the model write the cut card's options.** An option the model writes
can name a cut in words with no number. Its pick then binds no bound, and the
question comes back for each study. Code builds the options, so each label
carries the bound it binds, and a picked tail carries over to the next study.

**Raise the card only from a refused export.** The guard builds the card
when `create_eda_step` sends a filter whose bound no one stated. With no
stated cut the model sent the export with no filter at all, which is refused
as a subset that names no gene entity, and then wrote its own question. An
instruction to send a guessed filter did not change that, so the card has a
tool of its own.

**Carry a picked tail to any numeric variable.** A low tail picked on a
fitness score, where more negative is a stronger defect, was applied as the
lowest values of a rank on another study. Whether rank 1 is the strongest
defect is the study's own convention, which code cannot read, so the rule
holds only for a variable of the same display name.

**Read a published cutoff from the study's description.** A description is
prose, and reading a cutoff from it needs a model to understand the text. The
offer reads distributions only.

**Keep one computation in the analysis.** The write replaced the whole list,
so a compute run deleted the plots a researcher made in the site's EDA app,
and every reader took the first computation as the comparison, which on a
site-edited analysis is a `pass` compute.

**Count the gene entity's rows and call them genes.** A filter on the sample
entity restricts the counts entity to the rows of those samples, so the count
is not zero, and the preview reported it as a gene count: 535,832 of 1,266,512
rows under a 44-sample subset, while the exported step answered 0 genes on the
site. The rule reads which entities the filters name, which needs no count,
and the count it does take is distinct gene ids, never rows.

**Take the gene entity's declared `distinctValuesCount` as the denominator.**
It matched the service on both recorded studies, but it is metadata, and the
filtered count needs the distribution anyway, so both numbers come from the
same kind of read.
