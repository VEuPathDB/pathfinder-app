---
type: Decision
title: An EDA analysis is a criterion of the spec
description: An exported EDA step is a criterion that carries an AnalysisBinding (dataset, comparison, method, direction, thresholds, subset sentences, words, and the step's document as an opaque value) and states no parameter of its own. FRAME reads it as bound and cannot re-bind, drop or leave it out of the structure. A comparison only the analysis workflow realizes waits in the spec under FRAME's own id with needs_analysis_on, and create_eda_step(criterion_id=...) binds it where the structure places it. Teaching FRAME to bind EDA searches, keeping EDA steps outside the spec, keying the handoff on the analysis id, and matching a fold-change criterion to the step by its words were rejected.
tags: [eda, agents, strategy, spec]
generated: { by: claude-code/opus-5, at: 2026-09-23T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-23T00:00:00Z }
status: stable
---

# What was decided

**An export is a criterion stated by what it selects.** `Criterion.analysis`
is a `domain/strategy/analysis_binding.py::AnalysisBinding`: the dataset, the
comparison and its method, the direction, both thresholds, the subset as one
sentence per filter, the words that say all of that, and the step's own
parameters as `step_parameters`, carried the way a saved strategy's subtree is.
`resolved_params` stays empty, so the document never appears where a spec
value is read. The criterion's search is the export's own
(`GenesByEdaVizWithCompute` for a compute export, `GenesByEdaSubset` for a
subset export). `create_eda_step` takes no search name: a dataset-specific
EDA-backed search is one FRAME meets in the catalog and turns into a waiting
criterion, never one an export writes. `Criterion.step_parameters` is what a build or an edit writes
on its step, and the fold never treats one export as an option of another.

**The kind is stored with the step, and the reader is pure.** WDK picks a
step's bridge plugin by the QUERY its search runs, never by the search's
name: a per-dataset `GenesByRNASeq...DESeq` search runs the compute query,
and a WGCNA module search declares the analysis parameter and never reads
it. A step's `AnalysisKind` (`compute`, `subset`, or `none` for a query that
never reads the document) is PathFinder's own per-step fact, so it is stored
beside the researcher's words in `StrategyAst.metadata`
(`domain/strategy/step_words.py::StepWords.analysis_kinds`, held on
`StrategyGraph.analysis_kinds`). Each entry is a `StampedKind`: the kind and
the search it was read for. Every reader (`StrategyGraph.analysis_kind_of`,
`StepWords.kind_of`) treats a kind read for another search than the step
runs now as absent, so a step whose search changes under the same id, in an
edit that rebinds it or a build that reuses its id, is read again; a step
that keeps its search keeps its kind. A stored entry that does not parse is
absent too (`OnErrorOmit`), so a load keeps the words and the step is read
again. It has the words' lifecycle: the graph
writes it into every tree it serializes, so `answered_graph` carries it after
every write; a load reads it back; a rolled-back batch puts it back; a step
that leaves the graph takes it with it. It is stamped where a step enters a
graph: the export knows its own kind and passes it through the commit, and a
step from VEuPathDB (an import through `wdk_sync.fetch_and_convert`, a step
the site read adds) takes it from the catalog through the tool server's
`eda_backed_search(definition)` (`is_compute_backed`, `reads_the_spec`),
which `services/eda/analysis_kinds.py::kind_of_search` turns into a kind. A read that fails the ways the catalog's
own loader names (`VEuPathDBError`, `OSError`, `RuntimeError`) leaves the kind
unset and the write goes on. A build stamps the same way every step it
mints under a new id, which covers a rebuild after a clear and a saved
strategy's clone, whether the insert route or FRAME's saved criterion brought
it; a duplicated step copies its source's kind and search with no catalog
read. An edit mints no step that carries an analysis document: a bound
analysis already has its step and a waiting one is the export's to write. A re-import stores the site's tree, so what
the thread stored is lost and each kind is read again. A step with no kind (a
tree stored before kinds existed, a step the canvas added) is stamped once at
the turn entry in `pre_turn`, and the next write stores it. Every catalog
stamp on a graph goes through `services/eda/analysis_kinds.py::read_the_unread_kinds`:
the turn entry, a build, the site read, and VERIFY's `check_study_step` and
`get_strategy`, so a step whose search changed within the turn is read before
it is judged. Three stamps read no graph: an import reads the kinds of the
tree it converts through `analysis_kinds_of`, the export states its own kind,
and a duplicate copies its source's. A search whose catalog read fails is not
asked again for the rest of the turn (`StrategyGraph.unreadable_searches`,
never stored; it belongs to the graph each turn builds). A step the catalog still cannot
read is reported as unread, never as no study step: `check_study_step` says
so, and `get_strategy` lists it under `unread_analyses`. VERIFY sets its
verdict from the other checks and names that step in its caveats, and the
runtime writes the same steps, read from the strategy and never from the
checker, into `VerificationDigest.pending_checks`. A pending check is neither
a pass nor an objection: `VerificationDigest.passed` is `success` with no
pending check, and every reader of the verdict reads it (the verified marker,
the memory gate, the eval verdict, the curated expectation and the ledger's
`successful`). The full ledger section and the budget verdict say "passed, N
check(s) pending", the compact ledger adds a `pending_checks` line, and the
rail shows the count where a pass would show a check mark, and the VERIFY
card reads "Passed, N check(s) pending". While a check is pending, a sentence
that names the site is not site blame when it also names a pending step or
says the site did not describe or could not read it; every other sentence
that names the site is judged as before.
`services/eda/export.py::exported_analysis(kind, parameters)` is pure. The
subset plugin reads only `descriptor.subset.descriptor`, so a `subset` step
binds its subset and no cut, whatever volcano the document stores.
`GeneEdaVizWithComputePlugin.findVolcanoComputation` takes the first
computation that holds a volcano with both thresholds, wherever it stands,
and reads the cut from that computation's first visualization; a `compute`
step binds that cut, and the comparison when that computation is a complete
differential expression. A `none` step, and a step with no kind, exports no
analysis. The domain imports no `veupathdb.eda`, so the reader is in
services.
`ai/lead/answered_strategy.py::analyses_of` reads the live tree into a mapping
the hydration, the replay and the one-time statement consume. The binding
names no analysis: an analysis holds one comparison beside any pass computes
the site stored, and each compute replaces that comparison, so two exports of
different comparisons share an id, and the document a step carries names
none.

**The diff compares meaning.** `spec_diff` compares a binding without its
document. A binding that selects other genes is a restated binding, which an
edit writes as the whole new document.

**FRAME keeps an analysis.** Its workspace and the edit work order print a
bound analysis as its words and `analysis workflow, BOUND: keep it; do not
re-bind, drop, or restate this comparison with another search`, with no
parameter. `set_criterion` on that id is refused with nothing recorded,
`drop_criterion` is refused because the Lead removes it with `delete_step`,
which the researcher approves, and `set_structure` refuses a tree that leaves
out a bound or a waiting analysis criterion.

**A comparison FRAME cannot realize waits under its own id.** When
`set_criterion` meets an EDA-backed search, the criterion enters the draft with
`needs_analysis_on=<dataset>` and FRAME places its id in the structure. A
search that names no dataset asks FRAME for one first, and a search on
another dataset than the one a waiting criterion names is refused: the
criterion keeps the dataset its analysis workflow opened. `set_criterion` that
binds a waiting id to any other search or to a saved strategy is refused:
only the export binds it. `build_strategy` mints
every other criterion; `run_edit` plans against the spec without waiting
criteria and records that spec as the answer, while the plan keeps them, and
no later edit owes a disposition for one (`the_edit_the_strategy_owes`). The
Lead's pinned route and the turn contract name the criterion's id, and
`create_eda_step(criterion_id=...)` binds it: the id must name a waiting
criterion on the analysis's dataset, the step joins the strategy's root under
the operator of the root combine the structure hangs it from (the root join
`spec_hydration.root_join_operator` reads), the criterion takes the step's id
and its binding on the plan, the answer and the dispatch record, the turn's
entry spec takes the same id so the turn's diff reads the criterion as changed
and not as dropped, and any other place is refused with the structure's
reason. `StrategyDomainState.restate_every_record` does that for the export
and re-keys the same records for `build_strategy`, so a resumed dispatch
never plans against a criterion whose step exists.
An export on a dataset a criterion waits on that names no criterion is
refused. An export on a thread with no spec states one.

**The turn entry states every analysis once.** `ai/lead/pre_turn.py` runs
`spec_hydration.analysis_criteria_stated` on all four specs: a criterion whose
step reads as an export gains its binding and loses the document it carried,
and a drop an earlier release recorded on an analysis dataset leaves every
record when a live export on that dataset answered it, and otherwise becomes a
criterion waiting at the root under INTERSECT, the join that release routed it
to; a second drop on one dataset folds into the first, and `OperationalSpec`
refuses a spec that names one criterion id twice. The rule reads only the drop and the live steps, so the four records agree.
A stated spec is returned as it is, so the statement needs no flag.

# What was rejected

**Teaching FRAME to bind EDA searches.** The search's parameter is a whole
analysis document that only the compute and filter calls produce. FRAME would
become a second writer of analyses, with thresholds it invented.

**Keeping EDA steps outside the spec and special-casing `run_edit`.** The
steps that run a search are exactly the criteria; replay, case memory, the
ledger and VERIFY would each need the same exception, and a site edit to the
step could not be replayed.

**Keying the handoff on the analysis id.** Two exports share it, and the step's
document carries none.

**Matching FRAME's fold-change criterion to the EDA step by its words or by
similarity.** It needs a threshold and fails in silence.

**Keeping the document in `resolved_params`.** It put the graph's form where
the diff and FRAME's workspace read the spec's, which is how the measured turn
restated an exported comparison and left its step out of the structure.

# Anchors

`domain/strategy/analysis_binding.py`, `domain/strategy/operational_spec.py`,
`domain/strategy/spec_diff.py`, `domain/strategy/spec_hydration.py`,
`domain/strategy/spec_replay.py`, `domain/strategy/spec_reconciliation.py`,
`domain/strategy/step_words.py`, `services/eda/analysis_kinds.py`,
`services/eda/export.py::exported_analysis`,
`ai/tools/standalone/_frame_eda.py`, `ai/tools/standalone/_eda_step_criterion.py`,
`ai/tools/standalone/_eda_step_spec.py`, `ai/lead/edit_dispatch.py`,
`ai/lead/lead_pins.py::eda_route_blocks`,
`tests/unit/ai/lead/test_the_measured_deseq_turn.py`.
