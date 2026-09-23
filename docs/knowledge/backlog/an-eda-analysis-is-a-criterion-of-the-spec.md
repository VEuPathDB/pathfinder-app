---
type: Backlog
---

# An EDA analysis is a criterion of the spec

An exported EDA step's criterion is its search name plus the raw analysis document
as `resolved_params` (`ai/tools/standalone/_eda_step_spec.py`, hydrated the same
way in `domain/strategy/spec_hydration.py`). FRAME's workspace and the edit work
order print that document as a value to keep and nothing tells FRAME that the step
already is the comparison it names, so FRAME re-states the comparison as the
dataset's fold-change search and leaves the step out of the structure, and
`run_edit` refuses the plan as one that loses the step. The handoff for a
comparison only the analysis workflow can build is a `DroppedCriterion` keyed on
the dataset (`ai/agents/state.py::frame_record_drop`), and the first export clears
every drop on that dataset, so a second comparison on the same dataset has no
record and is filled with a fold-change search.

Measured on vectorbase (v0.2.0a12): "Find genes significantly upregulated at 24 h
post blood meal versus 18 h and 36 h" ran DESeq2 for 24 h vs 18 h (150 genes) and
exported the step; the re-frame for 24 h vs 36 h dropped it, VERIFY objected that
a branch had no significance filter, and the turn ended with two fold-change
branches and one analysis branch intersecting to 2 genes.

## Fix

A criterion carries an `AnalysisBinding` (dataset, comparison, method, direction,
thresholds, subset sentences, and the step parameters as an opaque value, like
`SavedStrategyRef.subtree`), and `resolved_params` stays empty for it. The EDA
tools bind it; FRAME reads it as bound, may not re-bind, drop or leave it out of
the structure. A comparison FRAME cannot realise becomes a pending criterion under
FRAME's own id with `needs_analysis_on=<dataset>`, placed in the structure, and
`create_eda_step(criterion_id=...)` binds it in place. `run_edit` plans with
pending criteria pruned. `spec_diff` compares the binding's meaning and never the
analysis id, because one analysis holds one computation that each compute replaces
and the step's document carries no id. A reader in `services/eda/export.py` turns
step parameters into a binding; `answered_strategy` reads the live tree into a
mapping the hydration, the replay and a one-time migration in `pre_turn` consume.
VERIFY renders the binding's words and reads a compute step's significance
threshold as its significance filter.

Rejected: teaching FRAME to bind EDA searches (a second writer of analyses with
invented thresholds); keeping EDA steps outside the spec (breaks "the steps that
run a search are exactly the criteria"); keying on the analysis id; matching by
words or similarity.
