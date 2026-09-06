---
type: Decision
title: Per-site catalogs are evicted under a budget, built one at a time, and the warm-up does not block the bind
description: DiscoveryService holds catalogs in an LRU over SITE_CATALOG_BUDGET_MB (512 by default), a process builds one catalog at a time, only the api rebuilds a stale one, the snapshots persist on a named volume beside the embedding rows, and the lifespan spawns the warm-up instead of awaiting it so uvicorn binds in seconds. Rejected - one process holding every index and serving the rest over MCP, parallel per-site encoding, a rebuild inside a capped container, readiness as the container healthcheck, and sizing the budget from process RSS.
tags: [infra, memory, startup, embeddings, availability]
generated: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
status: stable
---

# What was decided

**A budget, not a ceiling, bounds the catalogs.** `DiscoveryService` holds its
per-site `SearchCatalog` objects in a `cachetools.LRUCache` whose `getsizeof`
is `SearchCatalog.memory_bytes`, and whose `maxsize` is
`SITE_CATALOG_BUDGET_MB` megabytes (512 by default, set in compose for `api`,
`worker` and `wdk-mcp`). The least recently used site leaves when the budget is
reached and is rebuilt from disk on its next touch. A site whose accounted size
is larger than the whole budget is served and not held.

The accounted size is `1 MiB + 4 * payload_bytes`, where `payload_bytes` is the
serialized length of the snapshot the catalog was loaded from. Measured on
plasmodb in the `wdk-mcp` image on 2026-08-27: a 7.9 MB snapshot restored in
0.4 s, encoded nothing, and cost 27.6 to 29.9 MiB resident.

**Superseded 2026-08-29 by [embeddings are an API call and a Postgres record
manager](embeddings-are-an-api-and-a-record-manager.md).** The formula carried a
third term, `index.embeddings.nbytes`, worth 3.2 MB on plasmodb. The vectors now
live in Postgres, so a catalog holds none of them and the term is gone.

**One build at a time, and only in the api.** A module-level semaphore in
`veupathdb_mcp/catalog/discovery.py` admits one `_fetch_from_api` per process,
and a `KeyedLock` in `DiscoveryService` admits one build per site. Both the
cold load and the background refresh of a stale snapshot pass through them.
`CATALOG_REFRESH_ENABLED` is `false` on `worker` and on `wdk-mcp`: a build of
one site was measured at 2.977 GiB, which no 2 GiB container survives, so a
process that only serves reads the snapshot the api saved and never rebuilds
it. Measured on 2026-08-27 inside `wdk-mcp`: a site with a fresh snapshot
restores in 0.3 s and costs about 10 MiB, and a build of a site whose snapshot
was 84.8 days old exceeded the ceiling and the kernel killed the process.

**The snapshots persist.** `catalogs_cache` mounts over
`veupathdb-mcp/data/catalogs` in all three services, where the distribution that
reads them keeps them. Without it, every recreate served the image's snapshots,
found them stale, and refetched all fourteen sites; the refreshed snapshots died
with the container.

**Superseded 2026-08-29 by [embeddings are an API call and a Postgres record
manager](embeddings-are-an-api-and-a-record-manager.md).** This paragraph named
a second volume, `embeddings_cache`, holding the encoded rows. That volume and
the `.npz` files it held are deleted; the vectors are Postgres rows.

**The warm-up runs beside the server.** The lifespan spawns
`_warm_up_subsystems` instead of awaiting it, and the model loads inside it run
on a thread, so uvicorn binds in seconds: measured on 2026-08-27, a recreate
bound 43 s after container start with all fourteen catalogs preloaded in 5 s
and nothing encoded, and the api settled at 2.21 GiB against the 5.66 to
8.83 GiB read off the same container before. The container healthcheck is
`/health`, because what a compose dependent needs is a server that answers and
a catalog now loads on demand. `/health/ready` keeps reporting per-subsystem
and per-site progress for the UI's startup gate, and the spawned task carries a
done callback that fails every subsystem still loading with the exception's
text, so a warm-up death outside a step's own handlers reads on the endpoint
instead of sitting at "loading" forever.

**The precedent pass asks whether its caller is still there.** A stateless
streamable-HTTP call runs in the session manager's own task group
(`mcp/server/streamable_http_manager.py`, `_handle_stateless_request`), so the
request ending cancels nothing and no cancellation reaches the tool.
`rank_public_strategies_semantic` embeds `EMBED_BATCH` strategies per call and
scores each batch as it arrives, and `search_example_plans` passes an embedding
function that refuses once `Request.is_disconnected()` is true, so the work
stops at the next batch boundary. It also holds that site's lock for the whole
call, so a second caller queues rather than doubling the allocation. Measured
on 2026-08-27 against the served endpoint: three calls abandoned at a five
second budget all stopped about seven seconds after their clients left, the
container kept `RestartCount` 0 at 1.089 GiB, the next call answered 200, and a
patient client got its ranking in 46.2 s.

**Superseded 2026-08-29 by [embeddings are an API call and a Postgres record
manager](embeddings-are-an-api-and-a-record-manager.md).** `EMBED_BATCH`,
`_embed_while_connected` and the disconnect check are deleted. The site's
public strategies live in a `public-strategies:{site_id}` index, so a repeat
call embeds only the query and the 46.2 s pass is a sync of seconds; the
per-site lock stays, in `public_strategy_search`, so two callers do not sync
the same list at once.

**One document per model batch.** `fastembed` pads every text in a batch to the
longest one in it. Measured on toxodb: encoding 64 descriptions (median 378
characters, longest 6624) cost 166.5 s and 886 MiB at `batch_size=8`, and
128.9 s and 186 MiB at `batch_size=1`. The same eight-site sweep that the
kernel killed at the 2 GiB ceiling on its third site now finishes at
1375.8 MiB.

**Superseded 2026-08-29 by [embeddings are an API call and a Postgres record
manager](embeddings-are-an-api-and-a-record-manager.md).** There is no local
model and no padded batch. A request carries up to 256 inputs and 200,000
characters, and eight requests run at once.

# What was rejected

**One process holding every index, serving the rest over MCP.** The fork the
MCP execution plan records as decision point 4. It turns every catalog read
into a network hop and moves the same unbounded growth into one process that
still has no budget. The LRU bounds the growth where it happens, in every
process that has it.

**Parallel per-site encoding at startup.** A cold build of one site was measured
at 2.977 GiB under a 3 GiB ceiling and 3.269 GiB under a 6 GiB one. Running
fourteen of those at once multiplies exactly the peak the 2g ceilings exist to
bound. Serializing the builds is what makes the ceilings hold.

**Superseded 2026-08-29 by [embeddings are an API call and a Postgres record
manager](embeddings-are-an-api-and-a-record-manager.md).** The peak this
rejection bounds was the local model's arena. A sync holds up to eight HTTP
responses. The one-build-at-a-time semaphore stays, because a cold build still
fetches and holds a whole catalog.

**`/health/ready` as the container healthcheck.** It gated `web` on all fourteen
catalogs being preloaded, which is what turned a slow warm-up into an hour of
502 from the web proxy. A catalog is a cache, not a precondition: the endpoint
stays honest and stops being the gate.

**Letting every process rebuild a stale catalog.** It is what the measurement
refuses: one build needs about 3 GiB and both capped containers hold 2 GiB, so
a call that named a stale-cache site took the server down instead of answering.
The api carries no ceiling and already walks every site at start, so it is the
one process that can pay a build.

**Sizing the budget from process RSS.** The allocator does not return freed
pages, so a resident-set reading is not a per-site cost and a budget written
against it would evict on noise. The accounted size is derived from the
snapshot the catalog holds.
