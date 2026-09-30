---
type: Backlog
title: A continuous comparator is refused before submit
description: A differential-expression config whose comparator is a continuous variable with no vocabulary, compared by labels, passes the client's predicates and ends as a failed job; the predicates refuse it before submit and name the variable's data shape.
tags: [eda, compute, veupathdb-py]
generated: { by: claude-code/opus-5, at: 2026-09-30T00:00:00Z }
status: proposed
---

# A continuous comparator is refused before submit

**What I did.** Ran `run_eda_compute` with `comparator_variable` VAR_7033e90f
("temperature", `variable_type` integer, `data_shape` continuous, vocabulary
empty), `group_a_labels` ["30"] and `group_b_labels` ["37"], method DESeq.

**What I got.** The config passed `validate_compute_config`, the site's
compute service ran the job, and it ended `failed`. The service lists no file
for a failed job, so the job itself says nothing about why.

**Why that's wrong.** The researcher waits for a job that cannot succeed and
then learns only that it failed.

**Why it happens.** `veupathdb.domain.eda_compute_validation._comparator_errors`
checks labels against the variable's vocabulary only when it has one; a
continuous variable has none, so a label comparison on it is never refused.

**Fix.** The predicate refuses a label comparator on a variable whose data
shape is not categorical, and names the shape and the variable (the plugin
compares a continuous variable by bins). A veupathdb-py tag, then the pin bump.

**What you'd get.** The call is refused before submit with the reason, and no
job runs.
