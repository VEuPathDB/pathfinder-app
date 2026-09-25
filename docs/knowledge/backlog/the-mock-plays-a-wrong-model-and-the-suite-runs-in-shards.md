---
type: Backlog
---

# The mock plays a wrong model, and the suite runs in shards

## The wrong path

The mock arcs play a model that answers well. Nothing in the e2e suite plays a
model that answers badly, and the pre-UAT findings were mostly that: a value
passed as a parameter term, a search name the site does not list, a count the
strategy does not hold, a control id dropped from a tool call, a step deleted
that the researcher did not name, a site-switch question a conversation cannot
act on. Every one of those has a guard in the product (the enum refusal, the
rationale refusal, the turn contract's corrections, the card naming its step,
the portal-route sentence), and no spec proves the guard from the browser.

## What

- Fault-injecting arcs beside the good ones: for each guard, an arc whose model
  makes that mistake once and then follows the correction. The spec asserts what
  the researcher sees: the refusal or correction in the trace, the reply that
  states the corrected count, the card that names the step, no orphan step on
  the site.
- The arcs are selected by an explicit marker per flow (see the sibling card on
  the mock arcs), so a wrong-path spec and its happy-path twin share the flow and
  differ only in the fault.
- The guards' catalogue is `docs/knowledge/uat/findings.md` plus the refusal
  sentences the inventory listed under each family; each guard names its spec in
  the UAT coverage matrix.

## The time

Measured on the nightly run of 2026-09-25 (one `ubuntu-latest` runner, two
Playwright workers, 54 spec files):

| step | minutes |
|---|---|
| build and start the stack | 3.5 |
| Playwright run | 18.5 |
| whole job | 23.7 |

22 feature specs and the 5 journeys run serialized (`feature-turns` and
`journey` projects, `fullyParallel: false`), because "data-part waits starve when
every worker slot holds a turn": the mock stack's one worker process serves every
turn, so parallel turn-driving specs queue behind each other and time out.

## What

- Measure the starvation: raise the e2e worker's concurrency and run the
  turn-driving specs with `fullyParallel: true` at 2, 4 and 8 workers; record
  the failures per setting. The fix is capacity in the stack (one worker slot per
  Playwright worker, or a second worker container), not serialization.
- Shard across runners: a matrix of `--shard i/N` jobs, each starting the stack
  from images built once per run (build in one job, hand the images to the shards
  as an artifact or a registry tag), with the report merged (`playwright merge-reports`).
- Drop CI retries from 2 to 1 once the suite is stable, so a flake costs one
  rerun and not two.
- Target: the e2e job under 8 minutes on a push, with the same 167 specs.

## Done when

Every product guard the findings name has a wrong-path spec that fails when the
guard is removed; the turn-driving specs run in parallel; the e2e job's measured
duration is under the target on three consecutive runs.
