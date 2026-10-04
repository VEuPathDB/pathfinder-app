---
type: Decision
title: Statistics are the EDA service's computations
description: Every statistic a reply states about the samples of an open EDA analysis is a computation the VEuPathDB EDA service ran on the analysis's subset, read back as a typed model, shown as a part and named in the reply through the `stat` reference. A PCA is the dimensionalityreduction compute, run on the worker; a two-by-two table, a contingency table, a boxplot and a fitted line are the service's pass-through visualizations, read at once. Rejected - a code sandbox the model writes analysis code in, and statistics the model chooses and computes locally from rows it reads.
tags: [eda, statistics, pca, agent, facts, references]
generated: { by: claude-code/opus-5, at: 2026-10-03T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-10-04T00:00:00Z }
status: stable
---

# What was decided

A researcher who opens an expression study asks whether the conditions
separate, whether two sample variables are associated, or how a measurement
spreads by group. PathFinder answers each of these with a computation the
site's EDA service runs, never with a test or a model of its own:

- `run_eda_dimensionality_reduction` runs the service's `dimensionalityreduction`
  compute on the worker through the same settling path as differential
  expression (`services/eda/compute_jobs.py::settled_job`), reads the
  components the job generated (`/computes/dimensionalityreduction/meta`) and
  the samples on the first two of them (the compute's scatterplot), keeps the
  computation on the analysis, and puts a `data-eda.pca` part on the thread.
  Each component is named by the text the compute gives it, which states the
  variance it explains. The statistic also places each colored group on each
  component, its range and its mean, and states each pair of groups whose
  ranges on a component do not overlap. These describe the coordinates the
  compute returned for every sample; they test nothing, and the plot shows the
  same places.
- `read_eda_statistics` reads one of the service's pass-through
  visualizations on the analysis's own filters: `twobytwo`, `conttable`,
  `boxplot`, or a scatterplot with a best-fit line, and puts a
  `data-eda.statistics` part on the thread. A two-by-two table the service
  cannot evaluate is refused with the contingency table as the way on.

Each result is filed on the thread as a `StatisticFact` under an id the same
on every read of one kind and set of variables (`domain/statistic_facts.py`,
`StrategyDomainState.statistics`), so a later message's reply can name a
statistic an earlier message computed; the Lead's instructions list each value
under its reference (`lead_pins.pinned_statistics`). The reply states a value
only as `[stat:<id>.<row>]`, the renderer fills it from the fact, and a bare
number a statistic holds is a prose fault whose fix names the reference. A
statement a statistic makes holds no number, and the reply says it in words. A
component's row is the share of variance its label states, and a count row
carries its noun.

# Why

Every number a researcher reads must be a typed result they can check: the
same request against the same site returns the same value, and the analysis
document on the site holds the computation that produced it. A number the
model computed from rows it read is neither: nothing records the method, the
rows it read can be a sample of the subset, and a test the model chose is a
test the service never ran.

# Rejected

- **A code sandbox.** The model would write and run analysis code over rows it
  downloads. The code, the rows and the method live only in the run, so the
  researcher cannot repeat the number on the site, and a sandbox is a second
  execution surface to secure and to pin.
- **Model-chosen local statistics.** The model would pick a test and compute it
  from rows a tool returns. The test is the model's guess at what the service
  would have run, and a reply can state a test the service does not offer.
