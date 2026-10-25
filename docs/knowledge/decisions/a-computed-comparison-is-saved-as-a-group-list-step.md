---
type: Decision
title: A computed comparison is saved as a group list step
description: A compare that veupathdb-mcp answers on its computed route is held by a `groups:` handle and becomes a criterion on the site's group id list search, through the same criterion path a saved gene set takes, its ids uploaded to the researcher's account by `counted_id_list`; its counts are a `group_comparison` statistic the reply places with `[stat:]`. Inlining the ids, a step outside the spec, and a parallel step-building path were rejected.
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
the comparison is computed: the save is the researcher's to ask for. A framing pass that
holds an unsaved comparison ends with a card, "Save these 7,364 groups as a step?", whose
two options carry a `SaveComputedGroups` binding with the handle, so the researcher reads
no hash and the binding keeps the ids until the answer. `set_criterion(computed_groups=...)`
binds only on a turn whose intent asks for a strategy (`REQUEST_INTENTS`) or that picked
the card's save option (`TurnMarkers.saves_asked`), and a `groups:` handle bound as a
phyletic expression is sent back to be passed as `computed_groups`.

**The step.** `set_criterion(computed_groups=<handle>)` saves the ids with
`counted_id_list(..., record_type="group")`, which uploads them as an id list dataset in
the researcher's account, counts a `GroupsByNameList` step on it in an internal strategy,
deletes that strategy whatever the count, and refuses a list whose count is not the ids
(`IdListStepCountError`). That refusal is a failed call, not a retry: the ids come from the
site's own clouds, so a rebuild meets the same count, and the counted answer stands. The
criterion takes the returned search, record type and `group_names` dataset, as a saved gene
set takes `GeneByLocusTag` and its dataset (`_frame_gene_set.py`), so BUILD makes an
ordinary leaf of it that combines, transforms and counts in the step tally. Its title is
the question with "computed snapshot" and the day; its value's basis says the ids are fixed
and that a later release maps each id to the groups it became, so the step's count can
change. The comparison's reading check holds the computed criterion too
(`bound_comparisons`).

WDK's `DELETE /users/{id}/strategies/{id}` only marks the strategy row deleted
(`StrategyService.deleteStrategy` -> `StepFactory.updateStrategy`), and WDK does not track
which steps use a dataset (`StepFactory.cloneDatasetParam`), so the uploaded dataset the
criterion holds outlives the internal strategy, and no strategy is left in the account.

**The facts.** `HeldComparison.facts()` is `ComparisonFacts`, registered in
`FACT_SOURCES`, so every row takes its display form from its type: counts as numbers,
shares of the groups and of each set's genomes as percentages, the route as its words.
Its statements say the groups are a snapshot, that `ties` counts over every group either
set holds and is no part of the selected groups, and which species leads each set, or
that two species tie for it. A
framing pass records the statistic when the Lead applies the pass, and the Lead reads it
under its references.

**The reply.** A group that one set alone holds is absent from the other set, not larger
in it, so the count alone overstates the comparison. The turn contract's
`unplaced_breakdown` rule (`ai/lead/turn_contract.py`, over
`TurnRecord.comparisons`, each a `PlacedComparison`) reads the references the reply
writes, never its words. A reply that places the group count, as `[stat:<fact>.groups]`,
as the `[count:]` of a step bound to the comparison's dataset, or as `[root]` when that
step is the root, also places `[stat:<fact>.bothHeld]` and each one-sided count above 0,
`residualGroups` above 0, and `leadingSpecies` with `leadingSpeciesShare` of each set
whose `leadingSpeciesLeads` holds: one species has the most genomes alone and more than
`LEADING_SHARE` (a quarter) of them, so it weighs on the set's average. The refusal names
each missing path and is asked once per turn.

**On the site.** WDK shows the list search's own description on the step and lets a
client set only `customName`, `expanded`, `expandedName` and `displayPreferences` on it
(`PATCH /users/{id}/steps/{id}`). The strategy takes a `description` when it is created.
A build whose spec binds a saved comparison (`snapshot_note`) creates its strategy with
`SNAPSHOT_NOTE`: each step named as a computed snapshot holds a saved list of group ids,
the ids are fixed, and a later release maps each id to the groups it became, so the count
can change. The client's `update_strategy` sends no description, so a computed step added
to a strategy the site already holds leaves the description as it was.

**Refusals.** Every `ValidationError` of the computed route is the builder's own limit, a
retry. `GroupTagError` and `GroupCloudSumError` are data the site served that the
builder cannot use: a failed call, recorded against the phyletic search.

# Rejected

- **The ids in the tool return.** A genus comparison selects thousands of groups; the
  model reads counts and a handle.
- **Binding the counted step itself, or `frozen_step_id`.** WDK holds a step in one
  strategy, and the counted step belongs to an internal one; `frozen_step_id` keeps that
  strategy and caches its step. The criterion holds the dataset alone.
- **A step-building path of its own.** A criterion on the list search reaches combines,
  edits and the tally with no new code.

# What falsifies it

`tests/unit/ai/tools/test_a_compare_past_the_caps_is_computed.py` (the recorded genus
mean: 7,364 groups, 1,884 both held, 5,480 left only, 0 right only, 371 ties, 1,969
residual, 17 probe and 6 compute requests),
`tests/unit/ai/lead/test_a_computed_comparison_reaches_the_facts.py`,
`tests/unit/ai/tools/test_computed_groups_are_saved_as_a_step.py`,
`tests/unit/ai/tools/test_a_builder_limit_is_no_site_failure.py`,
`tests/unit/ai/lead/test_a_computed_breakdown_is_placed.py`,
`tests/unit/domain/strategy/test_a_comparison_names_its_breakdown.py`,
`tests/unit/ai/lead/test_a_snapshot_build_takes_its_note.py` and
`tests/unit/services/strategies/test_a_snapshot_strategy_carries_its_note.py`.
