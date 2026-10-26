---
type: Backlog
title: The last pushed round is checked live
description: The gene-certainty attribution, the resent-build bound and the per-organism singleton count across all of OrthoMCL were tested only against recorded turns; run them once live.
tags: [audit, orthomcl, live]
generated: { by: claude-code/opus-5.5, at: 2026-10-26T00:00:00Z }
status: proposed
---

# The last pushed round is checked live

## What happens

Commit f380eb090 gives a gene its own finding certainty and stops a refused build being resent unchanged. The singleton count was checked live only for one genus, not for every organism on the site.

## Done when

A live audit follow-up names a gene's own certainty; a live build refused once is not resent unchanged; 'which organisms have the most singletons' answers from a tally of the result step across all organisms.

## Live run 2026-10-26

- The all-organism singleton count passed: the result step's tally named the leading organism across 840 organisms.
- The audit follow-up could not be checked: for a request naming only genes, the Lead passed the site name as a genome to the audit planner, did not retry after its refusal, and answered from the investigator instead of starting a run.
- Facts rendered as bare values in prose ("no RNA-seq junction support 0", "preserves the reading frame yes").
