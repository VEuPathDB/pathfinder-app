---
type: Decision
title: A DESeq comparison with no sample or no replicate is refused
description: Before a differential-expression job is submitted, each group's samples are counted from the subset. A DESeq job is refused with both counts when a group holds no sample or when neither group has a replicate, unless the service already holds it complete. The source shows those two cases cannot run and stops nothing else, so one sample against a group with replicates runs. Limma is not refused, and the limma package was not read. A failed job keeps "no reason published" and states the counts, because its log names no cause. A floor of two samples per group, inferring samples from rows per gene and reading the job's input file were rejected.
tags: [eda, differential-expression, compute, refusal]
generated: { by: claude-code/opus-5.5, at: 2026-11-03T00:00:00Z }
verified: { by: claude-code/opus-5.5, at: 2026-11-03T00:00:00Z }
status: stable
---

# What was decided

**`run_eda_compute_impl` counts the samples of each group before a job starts.**
`services/eda/group_samples.py::group_samples` sends one `POST .../entities/{sample
entity}/count` per group, with the analysis's subset plus a `stringSet` filter of the
group's labels on the comparator. That is two requests per compute. Each took about
60 ms on QA, and no other request is added unless the check refuses.

The sample entity is the parent of the value variable's entity. The plugin reads the
same entity: `DifferentialExpressionPlugin.java` takes `meta.getAncestors(entity)`,
and index 0, "the immediate parent entity (sample entity)", is the record id of the
count matrix (`VEuPathDB/service-eda` at `b3bb8bac06de4340b4b2c21d9aa4a94d9b3de61f`).

**The refusal.** `too_few_samples` refuses a DESeq job when
`GroupSamples.has_an_empty_group_or_no_replicate` holds: a group has no sample, or
both groups hold at most 1. The Lead reads, for one such study:

> No DESeq job started. In this analysis, group A (procyclic form) holds 1 sample and
> group B (bloodstream form) holds 1 sample. A group with no sample, or two groups
> with no replicate in either, is not sent to DESeq. A repeat of this call gets the
> same answer. Tell the researcher these counts, or widen the subset or choose groups
> that hold more samples.

A job the service already holds as `complete` is not refused. The service's result
is a fact, so it wins over a reading of the source. Only a refused
comparison costs the extra `autostart=false` lookup.

**A count that cannot be read refuses nothing.** A service refusal, a transport
failure or an unexpected body gives no count, and the job runs as it did. The log line
names the failure's class and no upstream text.

A comparator that is not a string is not counted either, and its job runs. Every
comparator with a vocabulary in the seven studies read (the five below and the two the
client records) is a string, so a `numberSet` or `dateSet` count has no measurement. A
wrong count there would be a false refusal.

## What the source says

**The rule is read from the source. It is not an assumption.**

- `VEuPathDB/veupathUtils` at `7c7efd31538912701479bff3c325b9e901ccce00`,
  `R/method-differentialExpression.R::cleanComparatorVariable`, stops when no sample
  remains after the comparator subset and when fewer than two groups remain. It holds
  no replicate floor. A group with no sample therefore cannot run, for either method.
- `thelovelab/DESeq2` at `4ba3e3a159da872566d825609a119a7615069663`, `R/methods.R`
  lines 586 to 601, stops only when the design matrix has as many samples as
  coefficients: "same number of samples and coefficients to fit, so estimation of
  dispersion is not possible", no longer supported since v1.22. With a two-group
  design that is exactly 1 sample against 1.

**So a group with no sample and 1 against 1 cannot run, and nothing else is refused.**
1 against 31 passes both checks. A false refusal blocks a comparison a researcher could
have had, so that job runs, and if it fails the failed-job message states the counts.
No job of that shape was submitted, so its outcome is read from the source and not
measured.

**Limma is not read to its source.** The stops in `cleanComparatorVariable` apply to it,
and the `limma` package was not read, so limma holds no refusal here.

## Which methods are refused

The tool serves two methods on this path, and `eda_pca_impl` shares only `settled_job`
and `refusal_of`.

| Compute | Refused | Why |
|---|---|---|
| `differentialexpression`, `DESeq` | an empty group, or no replicate in either group | The source above, and the studies below |
| `differentialexpression`, `limma` | never | The `limma` package was not read. A failed limma job still states the counts |
| `dimensionalityreduction` | never | It has no groups |

## A failed job

**Its log names no cause, so the cause stays "not known".** The refusal keeps that
sentence, adds the group counts when they were read, and states no explanation. With
a registered token, three failed jobs on QA (one on each of microsporidiadb, fungidb
and hostdb) list `differential_expression_input`, `exception.log` and `input-meta`.
There is no `error.log` (404). Their three `exception.log` files are byte-identical: a
Java stack headed `voidEval failed, request status: error code: 127`, with no R
message. A guest token gets 403 on every `/jobs/` path. `exception.log` is not read at
run time, because it says the same thing for each of them.

**A repeated call is the same job, and the refusal says so.**
`EDACompute.getOrSubmitComputeJob` returns any existing job that is not `expired`, and
a job id is a hash of the request. So the refusal for a failed job states that the
same arguments return this same job, for both computes.

## Measured on QA

Counted with this code's request, with no compute job submitted:

| site | study | subset | group A | group B |
|---|---|---|---|---|
| tritrypdb | `STUDY_da32747f09` | assay type mRNA transcriptome | procyclic form: 1 | bloodstream form: 1 |
| microsporidiadb | `STUDY_ebe5b9c18d` | none | 8 hour: 1 | 64 hour: 1 |
| fungidb | `STUDY_93c159b846` | fungal stage mycelia, label Mycelia_T12 | normoxia: 0 | hypoxia: 1 |
| hostdb | `STUDY_833d16a0c8` | none | sporozoite: 4 | 13 time-point labels: 31 |

A subset filter and a group filter on one variable compose by AND: the tritrypdb count
with both on `parasite form` is 1. The recordings are
`tests/fixtures/eda/group_sample_counts.json`.

The hostdb comparison is not refused, so this check does not explain its failure.
Whether that job belongs to this comparison is not shown: an `autostart=false` lookup
of each comparison above answered `no-such-job`, so the arguments of the failed jobs
differ from these in some field.

# What was rejected

- **A floor of two samples in each group.** It would refuse 1 against 31, which passes
  both stops in the source.
- **Inferring samples from rows per gene.** The subset preview shows rows of the gene
  entity. Rows divided by distinct genes is an estimate, and a missing gene moves it.
  The sample entity's count needs no estimate.
- **One distribution of the comparator on its own entity.** That is one request, and
  it counts the comparator's entity. A comparator on a higher ancestor would count
  that ancestor, not samples.
- **Reading the job's input file.** `differential_expression_input` holds the tall
  table, one row per gene per sample, and it exists only after a job ran.
- **Reporting `exception.log` as the reason.** The same text heads every failed job
  read, so quoting it gives a researcher a Java stack and no cause.
- **Refusing a job the service already completed.** That would contradict the service.
