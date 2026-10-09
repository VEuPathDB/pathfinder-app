---
type: Backlog
title: QA sites need a pass for automated clients
description: BLOCKED on the VEuPathDB team. Outside the VEuPathDB network the QA sites redirect every service call to a pre-release login, so the e2e job and both nightlies stay disabled until automated clients have an agreed way through.
tags: [testing, e2e, live-lane, sites, ci, qa]
generated: { by: claude-code/opus-5.5, at: 2026-10-09T00:00:00Z }
status: proposed
---

# QA sites need a pass for automated clients

**Blocked on the VEuPathDB team.** Every automated test path reads the QA sites
([tests run against the QA sites](../decisions/tests-run-against-the-qa-sites.md)).
From outside the VEuPathDB network (a laptop, a GitHub runner) `qa.<site>.org` and
`q2.<site>.org` answer every service call with a 307 to
`https://veupathdb.org/auth/bin/autologin`, the "VEuPathDB BRC Pre-Release Login" page.
From the cedar host they answer 200. How an automated client passes that gate is the
team's decision; nothing in this repository guesses a cookie or a mechanism.

**Until it is solved:** the CI `e2e` jobs (`ci.yml`) and both nightlies
(`wdk-nightly.yml`, `mcp-nightly.yml`) stay disabled in GitHub, and `yarn wdk:live`,
`yarn wdk:record`, the EDA provenance recorder and the e2e stack do not reach QA from
outside the network.

**The work, once the mechanism is agreed:**

- Give the live clients the pass: the e2e stack (api, worker, the Playwright sign-in in
  `apps/web/e2e/global-setup.ts`), the pytest live lane, the served MCP endpoint in
  `mcp-nightly.yml`, and the recorders. Where the pass lives (a client header, a cookie
  jar, a runner inside the network) decides whether this is a change to the client
  library's release or to this repository.
- Re-record on QA every response that waits in `fixtures-production-backup-2026-10-09/`
  (the api's `tests/fixtures/wdk`, `organisms`, `eda`, `separation` and `controls`, the
  site-help run capture `tests/unit/devtools/site_help_mock_run.events.jsonl`, the web
  `__fixtures__/separationResult.json`, and `packages/spec/phyletic_conformance.json`),
  put each back where its test reads it, and delete the backup directory and its
  `.dockerignore` line. Every test that skips with "needs a QA recording: re-record once
  QA access exists" runs again. The production values of
  `apps/web/e2e/fixtures/eda.ts` wait there too; the five EDA specs now read
  `apps/web/e2e/fixtures/recordings/eda.json` (the `EdaRecording` shape in `eda.ts`), which
  a QA recording writes, and run once it exists.
- Re-measure every value a live test or an e2e spec pins on QA and record the new values
  with their QA build: the seeds' `measured` blocks under
  `apps/api/src/pathfinder/data/seeds/` (whose `dataset_url` links now name the QA web
  roots, mapped from the production `/a/` alias), the constants in `tests/integration/ai/test_a_bind_is_measured_live.py`,
  `tests/integration/eda/test_compute_polling.py`,
  `tests/integration/strategies/test_wdk_user_dataset_searches.py` (and the three
  `pathfinder-uat-*` uploads it needs on the account, on QA),
  `tests/integration/strategies/test_wdk_workbench.py` and `test_wdk_verification.py`,
  the client library's `site_search_stream_genes.json` and EDA provenance, and the zero
  count in `apps/web/e2e/uat/strategy-exceptions.spec.ts`.
- Re-enable the e2e jobs (set the repository variable `E2E_ENABLED` to `true`; `ci.yml` runs the e2e build and shard jobs only then) and the two nightlies (`gh workflow enable`), and read their first runs.
