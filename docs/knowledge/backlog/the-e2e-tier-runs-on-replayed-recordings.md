---
type: Backlog
title: The e2e tier runs on replayed recordings
description: The replay tier is built and the e2e tier stays off in CI until the first recordings are committed; a full record run against QA commits the set, E2E_ENABLED goes on, and five api tests still skip on two states QA does not hold on request.
tags: [testing, e2e, ci, qa, recording]
generated: { by: claude-code/opus-5.5, at: 2026-11-23T00:00:00Z }
status: proposed
---

# The e2e tier runs on replayed recordings

CI runs recorded tests only
([CI runs recorded tests only](../decisions/ci-runs-recorded-tests-only.md)). The
replay tier is built ([E2E replays recorded WDK](../decisions/e2e-replays-recorded-wdk.md)),
and `ci.yml` runs its build and shard jobs only when the repository variable
`E2E_ENABLED` is `true`, which it is not: `apps/web/e2e/wire/` holds no recording yet.
From outside the VEuPathDB network the QA sites answer every service call with a 307 to
the pre-release login, so the recordings reach QA from cedar, or through an HTTP proxy on
cedar (`WIRE_UPSTREAM`).

**The work that remains:**

- With `WDK_TEST_EMAIL` and `WDK_TEST_PASSWORD` exported (and, outside the network,
  `WIRE_UPSTREAM` and `WDK_TEST_TOKEN`), one QA run at a time: build the catalog
  snapshots (`scripts/e2e-wire.sh catalogs`), record the whole suite
  (`scripts/e2e-wire.sh record --all`), measure the set against the 40 MB cap, and commit
  it.
- Set `E2E_ENABLED` to `true` once the suite passes on replay alone, and read the first
  runs.
- Lift the five api tests that skip on the two states QA does not hold on request, a
  cached AI expression summary and a crashed VDI import, when the client library records
  them (`veupathdb-py: docs/knowledge/backlog/two-states-qa-does-not-hold-on-request-are-recorded.md`).
