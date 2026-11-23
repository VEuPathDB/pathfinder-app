---
type: Decision
title: CI runs recorded tests only
description: CI makes no live call to a VEuPathDB site or a model; every test it runs reads a recorded or replayed response, and nothing runs on a schedule. A test path that reaches a live site stays off until it reads QA and is recorded. The live nightly lanes for the WDK rules and the MCP admission run were rejected and deleted, and the recordings are refreshed by hand.
tags: [testing, ci, live-lane, sites, recording]
generated: { by: claude-code/opus-5.5, at: 2026-11-23T00:00:00Z }
status: stable
---

# What was decided

**CI makes no live call.** Every job in `.github/workflows/ci.yml` reads recorded or
replayed responses only: the unit and integration tiers read the recorded WDK and EDA
fixtures and the scripted model, and no job reaches a VEuPathDB site, a model provider or a
served MCP endpoint.

**Nothing runs on a schedule.** `ci.yml` runs on a push, a pull request and a hand-started
run (`workflow_dispatch`). A hand-started run is also the run that refreshes the recorded
API test durations: it adds `--store-durations` to each test group and uploads the merged
`.test_durations` as the `test-durations` artifact.

**A live test path stays off until it reads QA and is recorded.** The e2e tier stays
behind the repository variable `E2E_ENABLED` until it runs on replayed WDK recordings
(`docs/superpowers/specs/2026-11-23-e2e-replays-recorded-wdk.md`).
`node scripts/check-test-sites.mjs` refuses a workflow that runs a live lane: the
`live_wdk` marker, a served `veupathdb_mcp`, or the fixtures recorder.

**The live checks and the recordings run by hand.** `yarn wdk:live` runs the `live_wdk`
lane and `yarn wdk:record` re-records the pinned fixtures, from a host that reaches QA.
The monthly refresh of the WDK recordings is run by hand when the user asks, not on a
schedule.

# Rejected

**Live nightly lanes** (`wdk-nightly.yml` ran `pytest -m live_wdk` against the QA sites;
`mcp-nightly.yml` served the MCP endpoint and ran the conformance suite against it). A
live lane measures the site on the day, not the change, so a red run names QA load, QA
data or the pre-release login more often than a defect in this repository. The QA sites
redirect every service call from outside the VEuPathDB network to a pre-release login,
so both lanes stayed disabled and gave no signal. A nightly run also spends Actions
minutes and a reader's time on a run no change asked for. A confirmed drift is found by
the hand-run refresh, which compares the recorded requests with what QA now answers.

# What this costs

A drift in a site's answers is found when someone runs the refresh, not the next morning.
The recorded fixtures are only as current as the last refresh.
