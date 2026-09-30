---
type: Backlog
title: An export the graph editor added is named by the study
description: An EDA export PathFinder writes reads the study's names for its filters and its measured variable and the compute's counts of its cut; an export the graph editor or the site added is stated from its document alone, so its facts row names each variable by its id and its cut shows no second count.
tags: [eda, facts, strategy]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# An export the graph editor added is named by the study

**What I did.** Traced where an analysis criterion gets its binding. An export
`create_eda_step` or the analysis tab writes goes through `read_the_export`, which
reads the study and the compute's statistics, so the binding holds `shown_subset`,
`value_variable_name` and `tallies`.

**What I got.** A step the graph editor or the site added reaches the spec through
the pre-turn (`analysis_criteria_stated` over `exported_analysis`), which reads the
step's document only. Its facts row reads "Subset: VAR_84f17484 is one of wild type"
and each chosen cut says its count at another value is not measured.

**Why that's wrong.** The researcher reads a machine id where the study has a name,
and a cut the compute can count shows no second count.

**Why it happens.** `exported_analysis` is pure and holds no study; the pre-turn
states a binding once and never reads the study for it.

**Fix.** When the pre-turn states an analysis criterion that holds no names, read
the study and the compute once (`read_the_export`) and state the binding with them.

**What you'd get.** The same row an export PathFinder wrote shows.
