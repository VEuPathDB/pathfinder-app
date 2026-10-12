---
type: Backlog
title: The corpus holds no plan with an analysis below the root
description: BLOCKED on the QA sites admitting automated clients. No corpus case states two study analyses under one OR, and the requirement reports and the in-run corrections of FRAME are measured by replay and unit tests only; one full corpus run and two new cases close both.
tags: [evals, eda, frame, corpus]
generated: { by: claude-code/opus-5.5, at: 2026-10-12T00:00:00Z }
status: blocked
---

# The corpus holds no plan with an analysis below the root

Of 684 saved specs, 20 hold a criterion that waits for its analysis, and each
one is the root or an input of the root combine. A plan such as
`INTERSECT(search, UNION(analysis, analysis))` was refused at every export
until the export took its join from the structure
([an EDA analysis is a criterion of the spec](../decisions/an-eda-analysis-is-a-criterion-of-the-spec.md)),
and no case would have shown it.

[A pass names a requirement by its number](../decisions/a-pass-names-a-requirement-by-its-number.md)
is measured by a replay of saved FRAME requests and by unit tests. No full turn
ran on it, because the QA sites redirect a client outside the network to a login
([QA sites need a pass for automated clients](qa-sites-need-a-pass-for-automated-clients.md)).

**To do, once a stack reaches QA.**
- Add a case that asks for genes of one search that any of two or more study
  analyses on one site also returns, with the structure, step count and root
  count measured on QA.
- Add a case whose request names a property the site has no search for beside
  one it has, and expect the gap row in the held words and no refused pass.
- Run the whole corpus once and compare the count of FRAME dispatches that end
  in a refusal with the last saved run.
