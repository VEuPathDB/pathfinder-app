---
type: Backlog
title: A canvas save waits behind the count refresh
description: On a slow site one canvas edit shows "Saving..." for about 30 seconds while the previous edit's count refresh runs. WDK does not serialize the two requests, so something in the api process does.
tags: [canvas, wdk, latency, strategy]
generated: { by: claude-code/opus-5.5, at: 2026-10-18T00:00:00Z }
status: proposed
---

# A canvas save waits behind the count refresh

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

**So the turn-taking is inside the api process.** The save's own WDK calls in the log are
8 to 10 seconds apart, with the count refresh's calls between them: a lock not listed above,
or synchronous work that holds the event loop.

**The work:**

- Reproduce one save beside one count refresh in the api with each await timed, and name
  what the save waits on.
- Fix that, so a save takes about as long as its own WDK calls whatever the count refresh
  is doing.
- A test that holds the save's time when a count refresh is in flight.
