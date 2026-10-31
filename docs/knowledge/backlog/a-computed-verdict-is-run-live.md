---
type: Backlog
title: A computed verdict is run live
description: The verifying eval cases pass live on QA; no organism column body can be recorded, because QA answers the step byValue report on the organism column with HTTP 500.
tags: [verification, evals, live]
generated: { by: claude-code/opus-5.5, at: 2026-10-27T00:00:00Z }
status: blocked
---

# A computed verdict is run live

## What is open

- The organism check in `ai/lead/verify_checks.py` reads a root of more than 2,000 records
  with the byValue reporter on its `organism` column (`top` 200); no recorded body of that
  column exists, so its tests read the recorded organism vocabulary. Every root of the
  verifying cases holds at most 343 records, so their live replays read the organisms from
  the standard report and never send this reporter.
- QA refuses the request. `POST /users/current/steps/{id}/columns/organism/reports/byValue`
  with `{"reportConfig": {}}` answered HTTP 500 `Internal Error` (text/plain, 14 bytes) on
  QA VectorBase on 2026-10-31, for the 343-gene root of an S2 strategy, and on QA PlasmoDB
  on 2026-10-28. The body matches the input schema of WDK's `ByValueStringReporter`, which
  takes an object with one optional boolean. The fault is the site's; report it with the
  site bugs of backlog 54.

## Done when

The site answers the report with HTTP 200, and its body is recorded under
`tests/fixtures/wdk` as `step_column_organism_by_value.json` and read by the organism
check's tests in place of the vocabulary.
