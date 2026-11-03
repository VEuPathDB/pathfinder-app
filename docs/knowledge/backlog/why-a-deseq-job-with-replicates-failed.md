---
type: Backlog
title: Why a DESeq job with replicates failed
description: A DESeq comparison of 4 samples with 31 on hostdb is reported failed although the source shows no stop for it, and the failed job's files hold no R message. Nothing waits on this; settle it by running the subset through veupathUtils with the error visible, or by asking the team that owns the service.
tags: [eda, differential-expression]
generated: { by: claude-code/opus-5.5, at: 2026-11-03T00:00:00Z }
status: proposed
---

# Why a DESeq job with replicates failed

This is an open question. No work waits on it.

## What is not known

A DESeq job on hostdb `STUDY_833d16a0c8` with 4 sporozoite samples against 31 infection
samples is reported failed.
[The source stops only an empty group and 1 sample against 1](../decisions/a-deseq-comparison-with-no-sample-or-no-replicate-is-refused.md),
so neither stop explains it. That job's refusal keeps "the cause is not known" and
states the counts.

The job's files hold no R message. Three failed jobs on QA list
`differential_expression_input`, `exception.log` and `input-meta`, and each
`exception.log` is the same Java stack, headed
`jakarta.ws.rs.BadRequestException: voidEval failed, request status: error code: 127`.
The jobs are `0ace0ca174d3c1398651fd73c3ef3e3e` (microsporidiadb),
`3b45ebd2fc9e6b79f96599406e84cd1b` (fungidb) and
`6e87a7a9b077846fe8741298acfef8dd` (hostdb). Which comparison the hostdb job holds is
not shown.

## How to settle it

Either of these answers it:

- Pull that subset from QA and run `veupathUtils::differentialExpression` with the error
  visible, if R and DESeq2 are available. `DifferentialExpressionPlugin.java` in
  `VEuPathDB/service-eda` shows the calls that build its input.
- Ask the team that owns the service why that job failed, and whether R's message is
  recorded anywhere a client can read.

## What changes with the answer

- A readable R message replaces "the cause is not known" with that message, in
  `services/eda/compute_jobs.py::refusal_of`.
- A cause that a count can show adds it to
  `GroupSamples.has_an_empty_group_or_no_replicate`.
