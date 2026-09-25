---
type: TestPlan
title: UAT flows - resilience
description: A site that stops answering, a VEuPathDB refusal shown where it happened, a provider that refuses the researcher's key, the worker down, a network drop, and a very long conversation; what the researcher is told in each.
tags: [uat, flows, resilience, errors]
generated: { by: claude-code/opus-5.5, at: 2026-09-24T00:00:00Z }
status: draft
---

# Resilience (R)

R1 and R4 need the deployment operator; agree a window before the run. Each flow is once, on plasmodb unless stated.

## R1 - A site that stops answering (operator)

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Operator | Restart the api with one site's base URL pointed at a host that does not answer (a sites override through `VEUPATHDB_SITES_CONFIG`), leave the other sites as they are | Within `SITE_PRELOAD_TIMEOUT_SECONDS` (30 s) that site's catalog fails |
| 2 | `GET <api-url>/health/ready` | Read | HTTP 200, `status: "healthy"`, `notReady: []`, `degraded: ["<site>"]`, the site's catalog `{"ready": false, "error": "the site did not answer in time"}` (or `"the site could not be reached"`) |
| 3 | `GET <api-url>/api/v1/sites` | Read | That site `available: false` with the same `unavailableReason`; every other site `available: true` |
| 4 | App | F3 steps 2 and 3 | `Couldn't reach` in the menu; the notice in the content area |
| 5 | App, a conversation on another site | Send the S1 prompt | It runs normally |
| 6 | Operator | Restore the site | Within `SITE_RETRY_INTERVAL_SECONDS` (60 s) plus one load the site is `available: true`; the notice clears without a reload |

## R2 - A VEuPathDB refusal shown where it happened

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | The S2 canvas, the transmembrane node, `Edit step` | Set `Minimum Number of Transmembrane Domains` to `abc`, `Save` | Either the editor refuses the value before sending, or the step shows the site's refusal: the node's red dot, `This step cannot run` with the site's message, footer `Save failed`, topbar `Failed - Retry` |
| 2 | Same | Put `2` back, `Save` | `All changes saved`, 116 genes |

The site's refusal for that value, measured: HTTP 422 `{"level":"SEMANTIC","isValid":false,"errors":{"general":[],"byKey":{"min_tm":["'abc' must be a number"]}}}`.

## R3 - A provider that refuses the researcher's key

Needs personal keys on (A2). Expected: measure at UAT start.

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | A stored OpenAI key the provider then refuses (revoke it at the provider after A2 step 4) | Send any message | The turn fails: `Response failed` with `OpenAI refused the key you added, so nothing ran on it. Replace or remove your OpenAI key in Settings, under Provider keys.`; the deployment's key is not used instead |
| 2 | Composer | Read | Banner `OpenAI refused the key you added. Replace or remove it in Settings, under Provider keys.`; placeholder `A key you added was refused - replace it in Settings.`; `Send` disabled |
| 3 | Settings, `Provider keys` | Read | `...<hint> was refused by OpenAI. Replace it or remove it.` |
| 4 | A stored key whose account runs out of credit | Send any message | `Response failed` with `This key has no credit, so nothing ran on it. Add credit to the OpenAI account, or replace or remove your OpenAI key in Settings, under Provider keys.`; Settings reads `...<hint>: This key has no credit. Add credit to the OpenAI account, or replace the key.` |

## R4 - The worker is down (operator)

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Operator | Stop the worker | Within 30 s `GET <api-url>/health/system` reads `workerAlive: false`, `notReady: ["worker"]` |
| 2 | App | Read | Banner `The background service is not responding. New messages may take longer to answer.`; the app stays usable |
| 3 | Composer | Send the S1 prompt | The message is stored and waits; no error yet |
| 4 | Operator | Start the worker | The waiting turn runs and answers (479 genes); the banner goes |
| 5 | Operator | Stop the worker in the middle of a turn (after `Planning...` shows) | After about 60 s of silence the turn ends: `Response failed` with `The worker running this turn stopped, which an out-of-memory kill can cause. Send the message again to retry.` (a turn past its age limit reads `The worker running this turn stopped before it finished. Send the message again to retry.`) |
| 6 | Operator, then app | Start the worker; `Try again` | The turn runs again |

## R5 - A very long conversation

The Lead's history is compacted at 100,000 estimated tokens (about 400,000 characters), keeping at least the last two exchanges; the notes are compacted at 50 notes or 10,000 tokens. None of the measured conversations came near it (the longest held 5 turns), so this flow is not measured. Expected: measure at UAT start.

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | One plasmodb conversation | Build S2, then send 30 edits in turn (alternate `Change the transmembrane range to 1 to 99.` and `Change the transmembrane range back to 2 to 99.`) | Each answer is 288 or 116 genes as the range says (SP INTERSECT TM 1-99 is 288) |
| 2 | Same | Send `What did I first ask for, and how many genes does the strategy return now?` | The first request (the S2 prompt) and the current count, both right after compaction |
| 3 | Right rail `Progress`, `Context` | Read | The `Assistant` bar drops after the compaction and stays under its window |

## R6 - A network drop and a reload in the middle of a turn

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | New conversation | Send the S2 prompt; at `Planning...` switch the browser offline (DevTools, Network, Offline) for 60 s | The turn keeps running on the server |
| 2 | Browser | Back online, reload | The thread shows the finished turn (116 genes), or keeps following it if it is still running |
| 3 | Offline again | Click `Good response` on the reply | Toast `The rating was not saved.` |
| 4 | If the page lost the running turn | Read | Toast `This conversation stopped following the work it has running; reload the page to read where that work got to.` |

## R7 - VEuPathDB slow at sign-in

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Sign-in dialog, when the site is slow | `Sign in` | `Login failed. Please try again.` and a working retry. The debugger's login to plasmodb timed out once in about 60 logins during the measurements (`httpx.ReadTimeout`) |

## R8 - The monthly allowance is spent (operator)

| Step | Where | Do | Expect |
|---|---|---|---|
| 1 | Operator | Set account A's monthly limit below what it has spent | The quota pill turns red |
| 2 | Composer | Read | Banner `Monthly quota reached` with `You've used $<used> of your $<limit> monthly limit. New messages are paused until <Month D, YYYY>, unless every stage runs on a key you added in Settings, under Provider keys.`; placeholder `Monthly quota reached - try again after the reset date.`; `Send` disabled |
| 3 | Operator | Restore the limit | Sending works again |

Not measured. Expected: measure at UAT start.
