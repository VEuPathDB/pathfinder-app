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

**What is done.** Every recording a test reads is a QA recording, the production backup
is deleted, and every value the pytest live lanes of this repository and of
`veupathdb-mcp` pin is measured on QA (a SOCKS tunnel through a host inside the network
reaches QA from a laptop: `ssh -D`, then `HTTPS_PROXY=socks5://...` with `socksio`).

**The work that remains:**

- Run the whole e2e suite against a stack that reaches QA and read every failure. The N4
  counts in `apps/web/e2e/uat/strategy-exceptions.spec.ts` hold on QA: 99 to 99
  transmembrane domains return 0 genes on PlasmoDB and VectorBase, and a minimum of 15
  returns 9 and 34.
- Lift the five api tests that skip on the two states QA does not hold on request, a
  cached AI expression summary and a crashed VDI import, when the client library records
  them (`veupathdb-py: docs/knowledge/backlog/two-states-qa-does-not-hold-on-request-are-recorded.md`).
- Give the live clients the pass, once the mechanism is agreed: the e2e stack (api,
  worker, the Playwright sign-in in `apps/web/e2e/global-setup.ts`), the pytest live lane,
  the served MCP endpoint in `mcp-nightly.yml`, and the recorders. Where the pass lives (a
  client header, a cookie jar, a runner inside the network) decides whether this is a
  change to the client library's release or to this repository.
- Re-enable the e2e jobs (set the repository variable `E2E_ENABLED` to `true`; `ci.yml`
  runs the e2e build and shard jobs only then) and the two nightlies
  (`gh workflow enable`), and read their first runs.
