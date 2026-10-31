---
type: Backlog
title: A failed differential-expression job says why
description: Four EDA differential-expression jobs on QA ended "failed" with no reason; three of them compared one sample with one sample or fewer, so the turn cannot tell the researcher that the comparison has no replicates.
tags: [eda, differential-expression, live]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: proposed
---

# A failed differential-expression job says why

## What I did

Ran suggested questions once on QA, one turn at a time, on Luna. Four turns
called `run_eda_compute` with `method: DESeq`:

| site | study | group A | group B | rows in the subset preview |
|---|---|---|---|---|
| tritrypdb | Procyclic and bloodstream form mRNA transcriptome and ribosome profiling | procyclic form | bloodstream form | 26,456 count rows for 13,228 genes: 2 samples |
| microsporidiadb | Time Series in Infected C. elegans | 8 hour | 64 hour | 2 values per gene: 2 samples |
| fungidb | A. fumigatus normoxia and hypoxia (mycelia, timepoint 12) | normoxia | hypoxia | 1 value per gene: 1 sample |
| hostdb | Host response to early and mid-stage P. berghei liver infection | sporozoite (4 samples) | 13 infection time-point labels (31 samples) | 35 samples |

## What I got

Every job ended `failed`. The tool returned, for example: "The
differential-expression job 6e87a7a9b077846fe8741298acfef8dd is failed. The site's
compute service publishes no reason for a failed job, so the cause is not known."
A second call with the same arguments returned the same job id and the same failure
(microsporidiadb job 0ace0ca174d3c1398651fd73c3ef3e3e, fungidb job
3b45ebd2fc9e6b79f96599406e84cd1b).

## Why that's wrong

The researcher gets "try again later" for a comparison that can never run: DESeq
needs replicates, and three of the four comparisons hold one sample per group or
fewer. No strategy is built and the reply does not say that the study design, not
the site, is the obstacle. Four suggested questions had to be removed for this.

## Why it happens

`jobs/impls/eda_compute_impl.py::run_eda_compute_impl` raises `refusal_of(job)` on a
failed job, and the EDA compute service publishes no reason; nothing counts the
samples in each group before the job is submitted.

## Fix

Not decided. Count the samples of each group from the subset before the job is
submitted and refuse a group with fewer than two samples, naming the counts; for a
failed job with replicates (the hostdb case), read whatever the compute service
records for the job before reporting. Confirm with the EDA team that DESeq refuses
groups without replicates.

## What you'd get

For the tritrypdb question: "The study holds one procyclic and one bloodstream
sample in the mRNA transcriptome, so a differential-expression test cannot run."
