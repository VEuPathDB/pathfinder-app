---
type: Backlog
title: The last pushed round is checked live
description: The all-organism singleton ranking passed live; the gene-certainty attribution of an audit follow-up and the bound on a resent build have not run live.
tags: [audit, orthomcl, live]
generated: { by: claude-code/opus-5.5, at: 2026-10-26T00:00:00Z }
status: proposed
---

# The last pushed round is checked live

## What happens

Commit f380eb090 gives a gene its own finding certainty and stops a refused build being resent unchanged. The singleton count was checked live only for one genus, not for every organism on the site.

## Done when

A live audit follow-up names a gene's own certainty; a live build refused once is not resent unchanged; 'which organisms have the most singletons' answers from a tally of the result step across all organisms.

## Where it stands

- The all-organism singleton count passed live on 2026-10-26 (840 organisms) and again on
  QA with Luna on 2026-10-31 (`orthomcl-singletons-counted-by-organism`, 523,795 groups,
  ranked by `count_step_by_column`).
- The audit follow-up failed live on 2026-10-26: the Lead passed the site name as a
  genome. The code now limits a plan's genomes to the site's organisms
  (`ai/audit/held_genomes.py`) and retries a replannable refusal; no live audit follow-up
  has run since.
- No live run has exercised a build refused once.
- Still owed: one live audit run with a follow-up that asks a gene's certainty, and one
  live turn whose build is refused once.
