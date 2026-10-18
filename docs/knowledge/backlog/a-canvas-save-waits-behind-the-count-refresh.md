---
type: Backlog
title: A canvas save waits behind the count refresh
description: On a slow site one canvas edit shows "Saving..." for about 30 seconds, because the save's WDK calls take turns with the count refresh that the previous edit started.
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

**What is not the cause.** Neither request enters a search turn (`search_turn` is only
entered by a chat turn and a durable job), the client allows 4 searches per site at a time
and 64 connections, and the expensive-search lock covers only High Speed SNP and slow
searches.

**The work:**

- Find what makes the two requests take turns: the one WDK session both requests share
  (one cookie jar per site client), WDK's own per-user handling, or a lock not listed above.
  Measure one save with no count refresh in flight, then with one.
- Decide from that measurement whether a save cancels or waits for the count refresh it
  makes stale, or whether the count refresh uses its own session.
- A test that holds the save's time when a count refresh is in flight.
