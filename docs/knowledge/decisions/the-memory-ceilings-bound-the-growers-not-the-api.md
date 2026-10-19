---
type: Decision
title: The memory ceilings bound the worker and wdk-mcp, and leave the api uncapped
description: worker and wdk-mcp each cap at 2g in compose and in their quadlets; the api carries no mem_limit. The numbers come from measurement on the 11.42 GiB dev VM - api 6.54 GiB idle-warm and 7.18 GiB under load, worker 1.13 GiB fresh, wdk-mcp 194 MiB idle and about 60 MiB per warm-cache site. A 3g ceiling on wdk-mcp was rejected after it let the kernel OOM-kill the api; capping the api was rejected because no cap both fits the VM and clears its measured appetite.
tags: [infra, memory, docker, mcp, worker]
generated: { by: claude-code/opus-5, at: 2026-08-24T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-24T00:00:00Z }
status: stable
---

# What was decided

`worker` and `wdk-mcp` each declare `mem_limit: 2g` in `docker-compose.yml`
and `Memory=2g` in their estate units. The api declares no ceiling.

Both capped services load per-site catalogs and semantic indexes on demand, so
they are the two processes whose memory follows the sites a session touches.
The api's own appetite is bounded by its site list, because it preloads every
site at startup and then stops growing. The catalogs are now held under a
budget and built one at a time - see
[per-site catalogs are evicted under a budget](per-site-catalogs-are-evicted-and-the-warm-up-does-not-block-the-bind.md)
- so the ceilings are the backstop and no longer the only bound.

The measured budget on the 11.42 GiB dev VM:

| Process | Measured | Ceiling |
|---|---|---|
| api | 6.54 GiB idle-warm, 7.18 GiB under load | none |
| worker | 1.13 GiB fresh, 5.26 GiB after five sites | 2g |
| wdk-mcp | 194 MiB idle, +60 MiB per warm-cache site | 2g |
| web + db | 0.23 GiB | none |

The two ceilings sum to 4 GiB, which leaves about 0.6 GiB of headroom against
the api's idle-warm figure.

# What was rejected

**A 3g ceiling on wdk-mcp.** It was measured, not guessed: with 3g the server
reached 2.977 GiB while building one site's catalog from a stale cache, the VM
ran out, and the kernel OOM-killed the api (`Exited (137)`). A ceiling large
enough to survive a cold catalog build does not fit next to the api on this
VM.

**A ceiling on the api.** No number works. 7g is below its measured peak, so
the api would be the process killed, which is the failure the ceilings exist
to prevent; 7.5g plus the two growers exceeds the VM.

**Sizing wdk-mcp for the cold-build peak.** No split of 4 GiB gives wdk-mcp
the roughly 3 GiB a cold catalog build needs and still leaves the worker more
than its own 1.13 GiB baseline. At 2g a call that names a site whose cached
catalog has expired rebuilds that catalog inside the call, exceeds the
ceiling, and the container restarts in about three seconds without answering.
A warm site costs about 60 MiB and answers in under a second. The trade was
deliberate: a kill on the new server costs one retry, a kill on the api costs
the application. The eviction budget and the one-build-at-a-time gate have
since removed the trade, and this ceiling stays as the backstop.
