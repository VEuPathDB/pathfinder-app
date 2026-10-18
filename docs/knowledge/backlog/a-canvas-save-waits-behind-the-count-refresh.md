---
type: Backlog
title: A canvas save waits behind the count refresh
description: Once a search is marked slow, every read of a strategy that names it takes the deployment-wide expensive-search lock, so a canvas save and the count refresh read WDK one at a time.
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

**The cause, measured.** `runs_on_the_deployment_line` (`services/search_waits.py`)
sends every request that names a search `counts_slowly` marks through the one
deployment-wide expensive-search lock, and one count of 10 seconds or more marks the
search for an hour. The client treats a GET of a strategy or a step as a search
(`_ANSWERED_RESOURCE` in veupathdb-py), so every read of a strategy that holds a marked
search takes the lock: the save's reads and the count refresh's reads run one at a time.
Two concurrent GETs of one PlasmoDB QA strategy finished together in 1.2 to 1.5 seconds,
and in 2.06 to 2.49 seconds once its search was marked, the second read waiting for the
first. Each wait is under the 5 seconds that logs one, so the log shows none.

**The work:**

- Decide what the deployment line holds once a search is only marked slow: every read of
  a tree that names it, or only the requests that make WDK run it.
- Change it, so a save takes about as long as its own WDK calls whatever the count refresh
  is doing.
- A test that holds two reads of a marked search's strategy to run together.
