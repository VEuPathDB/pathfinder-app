---
type: Backlog
title: A canvas save reads the same answers again
description: A parameter edit reads the definition of the search it edits three times, which is most of a 23 second save on PlasmoDB QA; the user id and the combine search are now read once.
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

**Also fixed.** veupathdb-py 0.1.0b14 keeps the user id and each combine's boolean search
on the site client, so a save no longer reads them again: on PlasmoDB QA through a SOCKS
tunnel, the four saves of the lifecycle test made 9 to 13 WDK calls in 9.6 to 23.3 seconds,
where they made 25 to 35 in 17.5 to 32, and the test passes.

**What remains, measured.** A parameter edit checks the search it edits: three plain reads
of the search definition (`GET /record-types/transcript/searches/GenesByGoTerm`, 1.3 to
3.1 seconds each) and four reads under the edited values (two contextual reads and two
dependent-parameter refreshes, 1.5 to 3.2 seconds each), about 15 of the 23 seconds of the
slowest save.

**The work:**

- Keep a search's plain definition on the site client, as the boolean search is kept, and
  release it with veupathdb-mcp. The reads under the edited values depend on those values
  and stay.
- A test that counts the definition reads of one parameter edit and holds the count.
