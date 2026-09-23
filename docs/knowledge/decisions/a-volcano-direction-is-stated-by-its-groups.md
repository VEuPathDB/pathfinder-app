---
type: Decision
title: A volcano direction is stated by the groups it keeps
description: A positive effect size in the EDA differential-expression app is higher in group B than in group A, and the WDK plugin keeps a positive raw effect size for upOnly, so upOnly keeps group B's genes. PathFinder keeps the app's upOnly/downOnly/upAndDown wire values and states every direction in the groups' labels wherever a model or a researcher reads it; one function in services/eda/direction.py names a compute export's step, and create_eda_step requires a caption for a one-sided export whose first whole-word label is the kept group's. Renaming the wire values was rejected.
tags: [eda, volcano, differential-expression, export, agent]
generated: { by: claude-code/opus-5, at: 2026-09-23T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-23T00:00:00Z }
status: stable
---

# The sign rule

The differential-expression compute takes `comparator.groupA` (the reference
group) and `comparator.groupB` (the comparison group). A positive effect size
means the gene is higher in group B. web-monorepo labels the two sides of its
volcano this way in
`packages/libs/eda/src/lib/core/components/visualizations/implementations/VolcanoPlotVisualization.tsx`:
the x-axis annotations are "Up in" group A at the minimum and "Up in" group B
at the maximum, and the legend shows "Up in" group B unless `effectDirection`
is `downOnly` and "Up in" group A unless it is `upOnly`.

The export applies the same rule. The WDK step reads the retained genes through
ApiCommonWebService
`WSFPlugin/src/main/java/org/apidb/apicomplexa/wsfplugin/eda/GeneEdaVizWithComputePlugin.java`,
whose `isRetainedRow` (lines 397-406) keeps a row that passes both thresholds
and then, for `UP_ONLY`, only when the raw effect size is above 0, and for
`DOWN_ONLY` only when it is below 0. So `upOnly` keeps the genes higher in
group B, and `downOnly` the genes higher in group A. The client library's EDA
bundle names the three values and does not state the sign.

# What was decided

**The wire values stay.** `upOnly`, `downOnly` and `upAndDown` are the app's
own vocabulary and travel inside the exported analysis spec, so they are not
renamed.

**Every surface states a direction by its groups.**

- `run_eda_compute` returns `comparison` (both groups' labels) and `signRule`,
  and its guidance counts each side as "higher in" a group's labels.
- `create_eda_step` documents the rule. Its result carries `selection`, for
  example "Kept 363 genes higher in 18h pbm, 36h pbm than in 24h pbm."
- A compute export's step is named by `direction_sentence`, the one builder
  in `services/eda/direction.py`. The model never names that step.
- The Lead's EDA loop states the rule in one sentence.
- The volcano legend, its accessible label and the direction choices name the
  labels ("Higher in 18h pbm, 36h pbm"). A thread part with no `comparison`
  falls back to the group letters.

**A one-sided export states its side, and the statement is checked.**
`create_eda_step` requires a `caption` for `upOnly` and `downOnly`; a two-sided
export may omit it. A label counts as named only as a whole word, compared
case-insensitively, so the "high" in "higher" does not name the label high. The
first label the caption names must be a label of the kept group. A caption that
names another group's label first is refused with the direction sentence, the
sign rule and the other direction. A caption that names no label is refused
with both groups' labels and no direction, because the fault is the caption,
not the direction. Nothing is written on a refusal. The check reads the order
of the labels because a caption such as "higher in 24h pbm than in 18h pbm"
names both groups, and only the first is the side it claims.

**Groups never share a label.** `run_eda_compute` refuses a label in both
groups before it defers a job, through its `args_validator`. The worker and the
tab's run both call the client library's `validate_compute_config`, which
refuses the same config, so no analysis this application writes holds an
overlap.

# What was rejected

**Rename the values to `higherInB`/`higherInA`.** The spec the step carries is
the app's own document, and the bridge plugin reads `effectDirection` from it.
A renamed value would have to be translated back at the boundary, and the model
would still meet the app's names in a stored spec.

**Let the model name the step.** A step name the model writes is a claim about
the data that nothing checks. The name is built from the groups and the
direction, so it cannot say the opposite of what the step holds.
