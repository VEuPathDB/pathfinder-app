---
type: Decision
title: A slow search is counted once
description: A search whose count takes ten seconds or more on a site is recorded slow for the process, and a bind of it reads no other value; every count is one request that waits as long as the client does, and one configuration in flight is sent once. A list of process-query searches and a per-search budget were rejected.
tags: [wdk, counts, measurements, load]
generated: { by: claude-code/opus-5, at: 2026-10-06T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-10-06T00:00:00Z }
status: stable
---

# What was decided

**A count that takes ten seconds marks its search slow.** `slow_searches.timed`
wraps the bind's own count (`wdk_counts.count_bound_criterion`) and every
measured reading (`measurements.TurnCounts`). A count that takes
`SLOW_COUNT_SECONDS` or more, or that is cancelled after that long, records
`(site, search)` in a process cache for `SLOW_MARK_SECONDS` (an hour). The mark is
shared by every researcher on the process, because the cost on the site belongs to
the search; it lapses, so a slowdown that passes, or a slow count one request
provoked, costs the readings of that search for an hour and no longer.

**A slow search reads no other value.** `measure_binding` records each value it
would have measured as `not_measurable` with the reason that the site counts the
search too slowly. The bind's own count is still read and shown.

**The bind's count waits as long as the client does.** It carries no budget of
its own, so a slow search returns its count instead of being dropped and asked
again on the next bind. The client's per-site timeout ends it.

**One configuration is sent once per turn.** `TurnCounts` holds each count in
flight as a task, so two readings of the same values share one request, and the
bind's own count is stored before any reading runs.

These sit on the client's own limits in `veupathdb-py` (WDK-HTTP-005): a request
that runs a search waits for one of a few slots per site, and a 5xx or a timeout
is not sent again.

# Why

WDK keeps running a search after its client stops waiting. A process query such
as a High Speed SNP Search starts about a thousand processes on the site, and
the measured readings of one bind sent up to a dozen configurations at once,
each a new search, each dropped at the reading budget while the site kept
running it.

# What was rejected

- **A list of process-query searches.** ApiCommonModel defines process queries
  in many query files (SNP, variant, BLAST, motif and others), and WDK's search
  metadata does not say which searches use one. A hand-kept list drifts; how
  long a count takes is measured on the site itself.
  The one-at-a-time line for expensive searches does read a list, the High Speed
  SNP searches `veupathdb-py` derives from ApiCommonModel (WDK-HTTP-006), beside
  the searches marked slow here
  ([decision](an-expensive-search-waits-in-one-line-across-the-deployment.md)); which
  values a bind reads is still decided by the measured count alone.
- **A longer measurement budget for slow searches.** Every reading of a slow
  search is another slow search on the site; a longer budget only lets more of
  them finish.
