---
type: Backlog
title: The last pushed round is checked live
description: The all-organism singleton ranking and the audit follow-up passed live; the bound on a resent build has not run live.
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
- The audit follow-up passed live on 2026-10-26 at 19:44 UTC, after the genome fix: the
  run on Afu2g18040 and NCU00776 stored a medium-certainty finding, and the follow-up
  "What did the audit find for Afu2g18040, and how sure is it?" answered medium
  confidence.
- No live run has exercised a build refused once.
- Still owed: one live turn whose build is refused once. In 77 suggestion runs on
  2026-10-31, 14 calls failed and none was sent again with the same arguments; none of
  them was a build.
