---
type: Backlog
title: A computed verdict is run live
description: The verifying eval cases pass live on QA; record one organism column body now that the organism check counts the organism_full column.
tags: [verification, evals, live]
generated: { by: claude-code/opus-5.5, at: 2026-10-27T00:00:00Z }
status: proposed
---

# A computed verdict is run live

## What is open

- The organism check in `ai/lead/verify_checks.py` reads a root of more than 2,000 records
  with the byValue reporter; no recorded body of that column exists, so its tests read the
  recorded organism vocabulary. Every root of the verifying cases holds at most 343 records,
  so their live replays read the organisms from the standard report and never send this
  reporter.
- The check named the `organism` column, whose byValue report the sites answer with HTTP 500.
  The countable column is `organism_full`, which the site's own organism filter uses; on one
  QA PlasmoDB step `organism` answered 500 and `organism_full` answered 200. The check now
  counts `organism_full` (pull request 37).

## Done when

The byValue body of `organism_full` on one step is recorded under `tests/fixtures/wdk` and read
by the organism check's tests in place of the vocabulary.
