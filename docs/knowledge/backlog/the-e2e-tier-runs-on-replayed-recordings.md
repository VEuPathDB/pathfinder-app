---
type: Backlog
title: The e2e tier runs on replayed recordings
description: The e2e tier stays off in CI because it reaches live sites; it runs again once the stack replays WDK answers recorded on QA, and five api tests still skip on two states QA does not hold on request.
tags: [testing, e2e, ci, qa, recording]
generated: { by: claude-code/opus-5.5, at: 2026-11-23T00:00:00Z }
status: proposed
---

# The e2e tier runs on replayed recordings

CI runs recorded tests only
([CI runs recorded tests only](../decisions/ci-runs-recorded-tests-only.md)). The
Playwright tier reaches live sites, so `ci.yml` runs its build and shard jobs only when
the repository variable `E2E_ENABLED` is `true`, and it is not. From outside the
VEuPathDB network the QA sites answer every service call with a 307 to the pre-release
login; from the cedar host they answer 200, and the whole e2e suite passes there.

**What is done.** Every recording a test reads is a QA recording, and every value the
pytest live lanes of this repository and of `veupathdb-mcp` pin is measured on QA.

**The work that remains:**

- Build the replay tier the design describes
  (`docs/superpowers/specs/2026-11-23-e2e-replays-recorded-wdk.md`): the stack replays
  committed QA recordings, and recording and the refresh run by hand on a host inside the
  network.
- Set `E2E_ENABLED` to `true` once the suite passes on replay alone, and read the first
  runs.
- Lift the five api tests that skip on the two states QA does not hold on request, a
  cached AI expression summary and a crashed VDI import, when the client library records
  them (`veupathdb-py: docs/knowledge/backlog/two-states-qa-does-not-hold-on-request-are-recorded.md`).
