---
type: Convention
title: UAT exit criteria
description: What "UAT passed" means for a PathFinder release - the severity scale, the pass rule, what a runner records per flow, how a count that moved on VEuPathDB is handled, and when a run stops.
tags: [uat, release, testing, exit-criteria]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: draft
---

# UAT exit criteria

## Severity

| Severity | Definition | Examples |
|---|---|---|
| Blocker | Data loss; a wrong count presented as right; a security or privacy breach; a flow that cannot complete. | The evidence card says `Supported` beside a count the site does not show. Researcher B sees researcher A's conversation. A turn ends in `Response failed` on a core flow twice in a row. A delete removes a strategy the dialog did not name. |
| Major | The flow completes, but an intermediate is wrong, a message misleads, or a broken layout hides information. | A trace row says `479 transcripts` for 479 genes. A refusal names the wrong site. The Strategy panel footer is cut off at 1024 px. |
| Minor | Wording, spacing, a glitch that blocks nothing. | Grammar (`1 steps`), a raw site id (`genes on plasmodb`), a tooltip that clips. |

A finding is scored once, at the highest severity it reaches on any site.

## The pass rule

UAT passes when all of these hold:

1. Every **core** flow (marked `core` in its family document) passes on every site in [sites and accounts](sites-and-accounts.md), with zero blockers and zero majors.
2. Every **non-standard** and **exception** flow passes, or fails with the expected refusal. A refusal the code renders is matched word for word. A refusal the model writes is matched on the facts its row names (the site, the organism, the search, the count), not on its wording.
3. Every deployment check (`D` flows) passes once on the test deployment.
4. At most **3 open minors per site** and **10 across the run**, counted after merging duplicates by root cause. The core flows are about 20 per site; three minors on one site means one screen in seven carries a visible flaw, which is where testers stop trusting the numbers beside it.
5. The data-hygiene sweep (`H1` in [runner checklist](runner-checklist.md)) leaves the test accounts empty of what UAT created.
6. Every finding in [findings](findings.md) is fixed and its flow re-run, or moved to [known limits](known-limits.md) by the product owner in writing.

## What a runner records per flow

| Field | Content |
|---|---|
| Flow id | as in the family document, e.g. `S2` |
| Site | site id, e.g. `plasmodb` |
| Build | the site's `buildNumber` read that day (see [sites and accounts](sites-and-accounts.md)) |
| Date and time | UTC |
| Account | `A` or `B` |
| Result | `pass`, `fail`, `blocked` (a prerequisite failed), `re-measure` (count drift, below) |
| Observed | every number the flow's `Expect` column names, as the app showed it |
| Conversation | the URL of the conversation |
| Cost and time | the `Conversation` usage pill after the flow; wall time from first click to the last expected result |
| Bug ids | one per finding, in the bug template of the [runner checklist](runner-checklist.md) |
| Evidence | a screenshot of the failing screen; the conversation JSON from `/export` for any `fail` |

Record results in the tally table of [the UAT index](index.md).

## A count that moved on VEuPathDB

VEuPathDB data changes between site releases. Every expected number in these documents carries the build it was measured on (build 71, released 20 August 2026, measured 2026-09-24).

| Situation | Rule |
|---|---|
| Same build, count equal | pass |
| Same build, count differs | The pre-release report reports `fail` here, because it cannot open the site; the runner decides between the two outcomes that follow. The runner opens the strategy with `Open in <Site>` on the evidence card. If the site shows the app's number, the expected number is stale: result `re-measure`, not a failure. If the site shows another number, it is a **blocker** (a wrong count presented as right). |
| New build, count within the tolerance | pass; write the new number and build beside the old one |
| New build, count outside the tolerance | same check on the site as above: `re-measure` when the site agrees with the app, blocker when it does not |
| Any build, the step layout differs | fail. The layout (searches, operators, transforms, their order) does not drift with data. |

**Tolerance:** the larger of 5 genes or 10 % of the expected count. Between two releases a genome annotation moves by tens of genes out of thousands; 10 % of a 116-gene intersect is 11 genes, which covers that churn, and 5 genes covers the small results (67, 25) where one re-annotated gene family moves the percentage a lot. A larger move means the data changed in a way the expected number no longer describes, so it is re-measured rather than waved through.

The evidence card's step table (`Recorded at the build` beside `On the site at the check`) is the app's own drift check: a cell marked `(changed on the site)` inside one flow is a finding.

## The stop rule

| Event | Action |
|---|---|
| A blocker on a site | Stop that site's run. Record it, run the hygiene sweep for that site, continue with the next site. |
| A blocker in a deployment check (`D` flows) | Stop the whole run. |
| The same blocker on two sites | Stop the whole run; the release is not a UAT candidate. |
| A major | Continue; the flow is `fail`. |
| A site marked `Couldn't reach` for more than 15 minutes | Mark that site's remaining flows `blocked`, not `fail`; the site is down, not the app. Run `R1` instead. |
