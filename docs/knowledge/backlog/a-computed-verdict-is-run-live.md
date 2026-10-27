---
type: Backlog
title: A computed verdict is run live
description: The verdict computed from the site was tested only on recorded bodies; replay the eval cases that verify before a push, and decide what a verdict means when the site does not answer the strategy read, since every site check is then unchecked and the verdict passes.
tags: [verification, evals, live]
generated: { by: claude-code/opus-5.5, at: 2026-10-27T00:00:00Z }
status: proposed
---

# A computed verdict is run live

## What is open

- The checks in `ai/lead/verify_checks.py` ran only against recorded WDK bodies and
  stubbed reads. The organism check reads the root's `organism` column with the byValue
  reporter at `top` 200; no recorded body of that column exists, so its values are the
  recorded organism vocabulary. Replay the corpus cases that verify (the S2 cases with
  `failedChecks` 0, and the OrthoMCL singleton ranking) on QA, one at a time, and record
  one organism column body.
- When the site does not answer the strategy read, `unread_checks` marks step validity,
  the bound values and the result count `unchecked`, so no check fails and the verdict
  passes. The researcher decides whether such a verdict is a pass, a pending check, or a
  stop that asks to run the check again.

## Done when

The replayed cases pass with the counts above, an organism column body is recorded under
`tests/fixtures/wdk`, and the unread-strategy verdict follows the rule the researcher chose,
with a test.
