---
type: Backlog
title: A canvas save reads the same answers again
description: A canvas save makes 25 to 35 WDK calls one after another, and reads the search list, the user id and the strategy again on every step, so one save takes 17 to 32 seconds on PlasmoDB QA.
tags: [canvas, wdk, latency, strategy]
generated: { by: claude-code/opus-5.5, at: 2026-10-18T00:00:00Z }
status: proposed
---

# A canvas save reads the same answers again

**Measured on PlasmoDB QA, a five-step canvas.** Each edit sends one
`POST /conversations/{id}/operations`, and the canvas then sends
`POST /conversations/step-counts`, which builds every step and combine of the tree on
WDK again. Every save took 26 to 33 seconds and every count refresh 23 to 34 seconds.
A change from Union to Intersect was still "Saving..." 30 seconds after the click.

**What the api log shows.** While a count refresh builds its steps, the save's own WDK
calls run between the count's calls, one at a time: the two requests take turns. The save
did one WDK call in its first 20 seconds.

**What is not the cause, measured.** WDK does not make these calls wait for each other.
On PlasmoDB QA, through the same client and cookie jar the api uses, each call alone took
0.9 to 1.25 seconds, and two at once finished together in 0.9 to 1.2 seconds, in one
session and in two: two answer reads, two step creates, and a step update beside a
strategy count. Neither request enters a search turn (`search_turn` is only entered by a
chat turn and a durable job), the client allows 4 searches per site at a time and 64
connections, and the deployment's expensive-search lock covers only reports and answered
reads of a High Speed SNP search or a search `counts_slowly` marks, never a step create or
a step update.

**What is fixed.** The canvas no longer counts the tree a second time after a save
(`features/strategy/services/countsWanted.ts`), and a read of a tree that names a search
marked slow no longer takes the deployment's expensive-search line
(`services/search_waits.py`). On PlasmoDB QA the lifecycle test sent one count request in
place of one per edit.

**What remains, measured.** A save alone still took 17.5 to 32 seconds on PlasmoDB QA
through a SOCKS tunnel, about 1 second for each of 25 to 35 WDK calls made one after
another. The operator change took 32 seconds:

| Call | Per save | Time |
|---|---|---|
| `GET /record-types/transcript/searches`, read to name a combine's boolean search | 2 | 9.1 s |
| `GET /users/current`, read again before most steps | 6 | 5.3 s |
| `GET /users/{id}/strategies/{id}`, the same strategy read again | 5 | 6.2 s |
| the combines, their reads, the step tree, the rename and the orphan deletes | about 10 | about 11 s |

**The work:**

- Read the boolean search's name, the user id and the stored strategy once for a save,
  in veupathdb-py where each read is made, and release it with veupathdb-mcp.
- A test that counts the WDK calls of one save and holds the count.
- Run `apps/web/e2e/journey/comprehensive-strategy-lifecycle.spec.ts` on PlasmoDB QA and
  read every save's time.
