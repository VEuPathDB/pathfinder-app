---
type: Decision
title: A computed comparison is saved as a group list step
description: A compare that veupathdb-mcp answers on its computed route is held by a `groups:` handle and becomes a criterion on the site's group id list search, through the same criterion path a saved gene set takes, its ids uploaded to the researcher's account by `frozen_step_id`; its counts are a `group_comparison` statistic the reply places with `[stat:]`. Inlining the ids, a step outside the spec, and a parallel step-building path were rejected.
tags: [orthomcl, phyletic, frame, strategy, facts]
generated: { by: claude-code/opus-5.5, at: 2026-10-25T00:00:00Z }
status: stable
---

# What was decided

`build_phyletic_expression` calls `veupathdb_mcp.wdk.answer_phyletic_pattern`. An
answer with `route: "expression"` is handled as before: an `expr:` handle that
`phyletic_expression` binds, a search the site re-runs. An answer with
`route: "computed"` (a whole-pattern compare past the expression caps, see veupathdb-mcp's
decision *a compare past one expression is computed from group clouds*) returns
`ComputedComparison`: the group count, `bothHeld`, `leftOnly`, `rightOnly`, `ties`,
`residualGroups`, each set's genomes, species, groups and proteins, the probe and compute
requests, a `factId` and a `groups:` handle. The group ids stay in
`computed_comparisons` (`domain/strategy/computed_groups.py::HeldComparison`). At the
turn end they are kept only while an open question, a declined proposal, a separation
offer or a pending approval names the handle, the check that keeps an `expr:` handle
(`ai/graph/expression_store.py`); the statistic outlives them. Nothing is uploaded when
the comparison is computed: the save is the researcher's to ask for, and a card that
offers it keeps the ids until the answer.

**The step.** `set_criterion(computed_groups=<handle>)` saves the ids with
`frozen_step_id(..., record_type="group")`, which uploads them as an id list dataset in
the researcher's account, builds a `GroupsByNameList` step on it and refuses a step whose
count is not the list (`IdListStepCountError`). That refusal is a failed call, not a
retry: the ids come from the site's own clouds, so a rebuild meets the same count, and
the counted answer stands. The criterion takes that step's
search and its `group_names` dataset, as a saved gene set takes `GeneByLocusTag` and its
dataset (`_frame_gene_set.py`), so BUILD makes an ordinary leaf of it that combines,
transforms and counts in the step tally. Its title is the question with "computed
snapshot" and the day; its value's basis says the ids are fixed and that a later release
maps each id to the groups it became, so the step's count can change. The comparison's reading check holds the computed criterion too
(`bound_comparisons`).

**The internal strategy stays, for now.** `frozen_step_id` keeps the step it made in
an internal strategy of the researcher's account and caches the step id per account and
membership, so a later call with the same groups returns that step. Deleting the
strategy after the read would leave the cache naming a step whose strategy is deleted.
WDK's `DELETE /users/{id}/strategies/{id}` only marks the strategy row deleted
(`StrategyService.deleteStrategy` -> `StepFactory.updateStrategy`), and WDK does not track
which steps use a dataset (`StepFactory.cloneDatasetParam`), so the uploaded dataset the
criterion holds outlives the strategy. Removing the strategy waits for a veupathdb-mcp
release whose id-list save deletes it and caches nothing.

**The facts.** `HeldComparison.facts()` is `ComparisonFacts`, registered in
`FACT_SOURCES`, so every row takes its display form from its type: counts as numbers,
shares of the groups and of each set's genomes as percentages, the route as its words.
Its statements say the groups are a snapshot, that `ties` counts over every group either
set holds and is no part of the selected groups, and which species leads each set, or
that two species tie for it. A
framing pass records the statistic when the Lead applies the pass, and the Lead reads it
under its references.

**Refusals.** Every `ValidationError` of the computed route is the builder's own limit, a
retry. `GroupTagError` and `GroupCloudSumError` are data the site served that the
builder cannot use: a failed call, recorded against the phyletic search.

# Rejected

- **The ids in the tool return.** A genus comparison selects thousands of groups; the
  model reads counts and a handle.
- **Binding the frozen step itself.** WDK holds a step in one strategy, and the frozen
  step belongs to an internal one; the criterion reuses its dataset instead.
- **A step-building path of its own.** A criterion on the list search reaches combines,
  edits and the tally with no new code.

# What falsifies it

`tests/unit/ai/tools/test_a_compare_past_the_caps_is_computed.py` (the recorded genus
mean: 7,364 groups, 1,884 both held, 5,480 left only, 0 right only, 371 ties, 1,969
residual, 17 probe and 6 compute requests),
`tests/unit/ai/lead/test_a_computed_comparison_reaches_the_facts.py`,
`tests/unit/ai/tools/test_computed_groups_are_saved_as_a_step.py` and
`tests/unit/ai/tools/test_a_builder_limit_is_no_site_failure.py`.
