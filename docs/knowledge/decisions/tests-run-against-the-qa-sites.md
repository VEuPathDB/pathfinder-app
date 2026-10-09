---
type: Decision
title: Tests run against the QA sites
description: Every automated test path that reaches a VEuPathDB site reads the QA sites file deploy/sites/qa.yml, and scripts/check-test-sites.mjs refuses a production or beta host in any test configuration. Production was rejected because test load took a production site down; beta was rejected because the production servers serve it.
tags: [testing, e2e, live-lane, sites, ci]
generated: { by: claude-code/opus-5.5, at: 2026-10-09T00:00:00Z }
status: stable
---

# What was decided

An automated test reaches the VEuPathDB QA sites (`qa.<site>.org/<project>.qa/service`),
never production. One file names them, `deploy/sites/qa.yml`, the file the estate's qa
stage reads.

- **The e2e stack** reads `e2e-sites.yaml`: the portal and the six component sites the
  suite drives, each entry copied from `deploy/sites/qa.yml`. The subset is kept because
  the boot warms every catalog the list names, and no spec opens the other seven.
  `docker-compose.e2e.yml` mounts it as `VEUPATHDB_SITES_CONFIG` for the api and the
  worker.
- **Every pytest run**: the root conftest sets `VEUPATHDB_SITES_CONFIG` to
  `deploy/sites/qa.yml` before anything reads settings, unless the environment names
  another file. The hermetic tiers read the same list, so every link a test expects is a
  QA link, and the integration tier's refusal guard refuses the QA hosts.
- **The nightlies** (`wdk-nightly.yml`, `mcp-nightly.yml`) set `VEUPATHDB_SITES_CONFIG`
  to the QA file at the top of the workflow, so the served MCP endpoint reads it too.
  `ci.yml` needs none: its e2e job reads the compose list, and its test job reads the
  conftest's default.
- **Recording**: the client's recorders (veupathdb-py 0.1.0b4) reach only the QA sites
  whatever the process names, and the EDA provenance recorder here reads the QA file
  unless the environment names another.
- **Every process names its list.** The client ships no default list since 0.1.0b4, and
  `Settings` refuses a process whose `VEUPATHDB_SITES_CONFIG` is blank. The compose stack
  defaults the api, the worker and wdk-mcp to `/app/config/sites/qa.yml` (wdk-mcp mounts
  `deploy/sites` there), the spec command and the docs build name the QA file, and each
  estate stage names its own.
- **The chat debugger** reads `--sites`, else `VEUPATHDB_SITES_CONFIG`, else the QA
  file. With `--via-worker` the file must be the one the worker reads.
- **The eval runner** requires `--sites` on every run. Its corpus counts were measured on
  production, so moving it silently to QA would change what a verdict means; the person
  who runs it names the sites each time. The thesis gold validator
  (`thesis/eval/scripts/validate_gold.py`) requires `--sites` for the same reason.

`node scripts/check-test-sites.mjs` holds this. It reads every file of the repository
except `docs/`, the backup directory, `thesis/`, the ignored local outputs and secret env
files, and fails on a production host: the bare site name, `www.`, `beta.`, the `auth.`
sign-in server or a numbered server. A mailbox such as a help address is not a host. It
also fails on a test site whose entry differs from the QA file, on an e2e service that
reads another file, and on a workflow that runs a live lane without the QA file at its
top level. Product data follows the same rule: the seeds' dataset links name QA web
roots.

No production data stays in a test path either. Every response PathFinder recorded from
a production site (`tests/fixtures/wdk`, `organisms`, `eda`, `separation`, `controls`,
the site-help run capture, the web separation result and the phyletic conformance file)
moved to `fixtures-production-backup-2026-10-09/` at the repository root, which no test,
build or image reads. A test that needs one skips with one reason, "needs a QA
recording: re-record once QA access exists", and only while that recording is missing
(`tests/_support/qa_recording.py`, `apps/web/src/lib/testing/qaRecording.ts`,
`apps/web/e2e/fixtures/eda.ts`), so a QA recording turns it back on with no code change.
No replacement is written by hand.

# Rejected

- **Production.** The tests ran there, and the load they put on a production site took
  it down for the researchers who use it. A test is not a researcher.
- **Beta.** `beta.<site>.org` resolves to the same server as production, so a test on
  beta loads production.

# What this costs

Outside the VEuPathDB network the QA sites answer every service call with a redirect to
a pre-release login. Until automated clients have a way through it, the e2e job and both
nightlies stay disabled
([QA sites need a pass for automated clients](../backlog/qa-sites-need-a-pass-for-automated-clients.md)).
Every expected count, identifier and vocabulary a live test or an e2e spec pins was
measured on production and is re-measured on QA once QA answers.
