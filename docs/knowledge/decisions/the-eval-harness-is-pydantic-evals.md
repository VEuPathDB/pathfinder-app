---
type: Decision
title: The eval harness is pydantic-evals, and the summary shape is ours
description: pydantic-evals ships with the pinned pydantic-ai and owns the dataset, the case loop, the evaluator protocol and the report; the machine-readable run summary is a local model, so a change of harness does not change the SLI feed. The run always drives the configured provider, and a recorded count is judged pass, re-measure or fail against the site build it was read on. Building a runner from scratch was rejected as a reimplementation of an installed library. The graded tree distance is now written in pure Python inside `pathfinder/evals/`, because taking it from the retired thesis harness would drag zss, numpy and scipy into the API image.
tags: [ws-v, evals, testing, observability]
generated: { by: claude-code/opus-5, at: 2026-08-23T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-23T00:00:00Z }
status: stable
---

# The spike, and what it found

`pydantic-evals` arrives at the same version as `pydantic-ai`, which hard-depends
on `pydantic-ai-slim[evals]`. The runner imports it directly, so `apps/api`
declares it directly too (`pydantic-evals>=2.22.0,<3`): a transitive package that
a module imports by name is a dependency whether or not it is written down. It
provides `Case`, `Dataset`, an
`Evaluator` protocol over a typed `EvaluatorContext`, concurrency control,
per-case duration, a failure list that separates a raised task from a failed
assertion, and a report. That is the whole of what a runner needs.

It is used for exactly that. `pathfinder.devtools.eval_runner` builds a
`Dataset[EvalCase, ObservedOutcome, None]` whose task drives a case's turns in
order on one thread, and whose single evaluator asks the corpus expectation.

# What stayed ours

**The summary.** `pathfinder.evals.summary.EvalRunSummary` is the run's
machine-readable result: harness, provider, assistant, timestamp, and one row
per case with its named differences. The observability contract reads this, and
it must not change shape because a library changed its report dataclass.

**The scoring.** `pathfinder.evals.scoring` is pure and unit-tested without a
database, a model or the harness. `score_case` returns every difference it
found, each naming the field, the expectation and the run's value, because a
boolean assertion answers "worse" without answering "how".

**The distance.** `pathfinder.evals.distance` is the graded answer beside the
boolean, and it is ours for the same reason the summary is: an eval trend that
depends on a third-party metric changes when that metric does.

# What was rejected

**A runner written from scratch.** It would be a dataset loader, a case loop,
a concurrency limiter and a report - all of it already installed and already
tested upstream.

**Taking the graded distance from the thesis harness.** An implementation
exists in `thesis/eval/scripts/tree_metrics.py` and it is not reusable here:
the thesis harness is retired by this program, and the module depends on `zss`
(Zhang-Shasha), `numpy` and `scipy` (Hungarian alignment), none of which the API
image carries. Three numerical packages in a production image, to compare trees
of five nodes, is the wrong trade.

**Leaving the verdict boolean.** Rejected once the corpus grew past four cases.
Exact structural match reports an operator swap and a strategy that shares no
search identically, so no trend drawn from it can say whether a change made the
assistant slightly worse or completely wrong.

# The distance, and where it lives

`pathfinder.evals.distance` implements the thesis decomposition in plain Python,
with no new dependency:

* **topology** - normalised Zhang-Shasha distance with every label erased, so it
  reads shape alone;
* **search selection** - Jaccard distance over the search names, combines
  excluded;
* **labelled** - normalised Zhang-Shasha distance where a differing search costs
  a whole edit, a differing operator costs 0.3 and parameter divergence costs up
  to 0.7;
* **parameter fidelity** - the mean agreement over searches the two trees share,
  or `None` when no shared search states values on both sides.

Zhang-Shasha is about seventy lines and needs no matrix library. The Hungarian
alignment the thesis used for parameter fidelity is replaced by pairing searches
by name in postorder, which is already an optimal name-only alignment and needs
no solver.

The expected side is parsed from the case's structure signature, so a case keeps
stating one readable string; `expected.parameters` names, per search, the values
that search must carry, and those are what parameter fidelity reads. Every case
result carries the four numbers, on a pass as well as on a failure: a trend is
drawn from how far a run moved, not only from whether it crossed the line.

# The run is always the configured provider

A run drives the model the deployment configures; there is no corpus run under
the scripted provider. The script routes on a token a Playwright spec writes
into its message, so a corpus prompt reaches it unmarked and answers nothing a
case could judge. What the scripted provider proves (routing, materialisation,
persistence, the shape the phases assemble) is the e2e suite's and the unit
tier's to prove.

# The verdict is a label, not a boolean

A case that records a count (`ExpectedOutcome.root_count`: the count, the site
build it held on, and the date read) is judged by `pathfinder.evals.drift.classify`
into one of three labels, which the harness records as its evaluator's output
and the summary counts beside passed and failed:

* `fail`: any difference that is not the count (a changed tree, a missing reply
  phrase, a wrong unit, a gate that did not come), or the count off on the same
  site build the case recorded, since the data is fixed on a build;
* `pass`: the count off on a new build and within `max(5, 10 %)` of the record;
* `re-measure`: the count off on a new build and outside that band, which is a
  re-measurement of the record and not a defect.

A boolean cannot tell a site release from a regression. The verdicts are read
by the person who runs the pre-release report: a `re-measure` is re-measured, a
`fail` is re-run once and then recorded as a finding. No workflow blocks on
them, because a real model's answer is a trend and not a gate.

# The promotion policy

Written into `conventions/verification-gates.md`, as ruled: an eval starts as a
tracked trend; it becomes a hard gate only after it catches or would have caught
a real regression and holds stable; a flaking gate is demoted or deleted, never
suppressed.
