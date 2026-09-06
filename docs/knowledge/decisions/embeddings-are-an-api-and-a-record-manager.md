---
type: Decision
title: Embeddings are an API call and a Postgres record manager
description: The local fastembed model is deleted. Every vector comes from OpenAI text-embedding-3-large at 1024 dimensions, batched and run in parallel, and lives in two Postgres tables addressed by the text that produced it. The api syncs the indexes; the worker and the MCP server only search them. Rejected - keeping fastembed with build-time .npz caches, bge-small, and a quantized nomic.
tags: [embeddings, infra, startup, memory, search]
generated: { by: claude-code/opus-5, at: 2026-08-29T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-29T00:00:00Z }
status: stable
---

# What was decided

**One embedder, and it is an HTTP call.** `embeddings/embedder.py` declares the
`Embedder` protocol and `EMBEDDING_DIMENSIONS = 1024`, the one width this system
stores. `OpenAIEmbedder` asks the API for that width, so nothing
truncates and nothing renormalizes: the API returns unit vectors, pgvector's
`<=>` is cosine distance, and `1 - distance` is a cosine in `[-1, 1]` everywhere.
Every input is cut at `EMBEDDING_INPUT_CHAR_LIMIT` (2000), grouped into requests
of at most `EMBEDDING_BATCH_SIZE` (256) items and 200,000 characters, and the
requests run under a semaphore of `EMBEDDING_REQUEST_CONCURRENCY` (8) with the
input order preserved. The client carries five retries and a 60 second timeout;
a batch that still fails raises `EmbeddingUnavailableError`, which names the
batch size and the cause.

**The width is a constant, not a setting.** `EMBEDDING_DIMENSIONS` is where 1024
is written: the embedder asks the API for it, and
`embedding_vectors.embedding` is declared `vector(1024)`. There is deliberately
no `EMBEDDING_DIMENSIONS` environment override, because a process that asked
for 512 would produce vectors the column rejects on every insert, and the
failure would arrive at a warm-up rather than at the setting. Changing the
width is a migration that alters the column and re-embeds, not a restart.

**One name for the sweep.** The function is
`record_manager.prune_orphan_vectors` and the periodic task is
`maintenance:prune_orphan_vectors`, registered in `jobs/tasks.py` with
`ORPHAN_VECTOR_GRACE`. There is no wrapper between them, so the concept has one
name in the code, in the task table and in the logs.

There are no query and document prefixes. They belonged to
`nomic-embed-text-v1.5`, whose asymmetric scheme the LangGraph store could not
express, because it routes both a put and a search through
`aembed_documents`. That trap is gone with the model.

**One record manager, and it is Postgres.**
`veupathdb_mcp/embeddings/record_manager.py` owns two tables.
`embedding_vectors(model, content_hash, embedding vector(1024), created_at)` holds
one row per model and text, so two indexes carrying the same text share one
vector. `embedding_index_entries(index_id, entry_id, content_hash, updated_at)`
holds membership. `sync_index` reads the current membership, computes
`sha256(model + "\n" + text)` per entry, embeds only the hashes with no vector
row, upserts the membership and deletes what is gone, in one transaction, and
answers with a `SyncReport(added, updated, removed, reused, embedded_texts)`. An
unchanged entry costs no API call. `search_index` ranks in SQL over the join of
membership and vectors; there is no in-memory matrix, no numpy ranking and no
per-process index cache, because an index is a few thousand rows.
`prune_orphan_vectors` runs daily from `maintenance:prune_orphan_vectors` and
deletes a vector no index has named for seven days.

The index ids are `catalog:{site_id}`, `eda-studies` and
`public-strategies:{site_id}`.

**The api syncs; the others search.** `EMBEDDING_INDEX_SYNC_ENABLED` is true on
the api and false on the worker and on `wdk-mcp`. The api syncs the fourteen
catalogs and the study index at warm-up and on a catalog refresh; a process with
the flag false builds its index entries and never writes them. The one index
outside that rule is the public strategies, because that list is fetched inside
the call that ranks it, so whichever process fetched it syncs it.

**A cosine is not the old dot product.** Two of the three "cosine" indexes
multiplied unnormalized vectors, so their scores ran to about 340 and the
catalog's `_SEMANTIC_BOOST = 15.0` multiplied that: the ranking was pure
embedding order and the lexical score did not participate. The boost is now
70.0 against a cosine, and the injection floor is a cosine of 0.35. Measured on
the plasmodb snapshot on 2026-08-29 over its 515 searches, the top lexical
`score_candidates` result of five research queries was 45.3, 106.9, 44.7, 49.2
and 60.4, with medians of the top ten of 42.5, 9.0, 16.2, 12.9 and 23.8. The
median top score is 49.2, and `0.7 * 70.0` is 49.0: a cosine of 0.7 is worth a
strong lexical match. A later calibration task refines this against a gold set.

**Degradation, everywhere.** An `EmbeddingUnavailableError` is never a 500. The
catalog search runs without the semantic bonus and logs once. The EDA study
search, and a study index with no membership rows, answer with the name-sorted
browse filtered by a case-insensitive substring of the query, with the guidance
"The study index is not built yet; results are matched by name only." The public
strategy ranking falls back to `rank_public_strategies`, the lexical one. Memory
retrieval returns no memories with a log line.

# Why

One fp32 model, `nomic-embed-text-v1.5`, was 547 MB on disk and 967 MB resident
per process before it encoded a single text, and it ran on CPU one sequence at a
time in the api, the worker and `wdk-mcp`. Measured 2026-08-29: rebuilding every
cache cold took about 110 minutes, of which the veupathdb portal alone was about
50; thirteen of the fourteen committed `.npz` files were in a shape the loader
rejected, so 7,184 of 7,699 shipped rows were dead; the quadlets persisted no
cache volume, so a deployment paid the whole encode again; and every
`search_example_plans` call re-embedded the whole public strategy list, which
took 46 seconds for a patient client.

# What was rejected

**Keeping fastembed with build-time caches.** It is the state this decision
replaces. The cost is not the download: it is 110 minutes of cold encode, about
1 GB resident in three processes, an OOM kill of the worker when a study index
was built on a turn, and a shipped cache format that thirteen of fourteen files
did not match. A build-time cache also has to be regenerated by hand, and the
regeneration is what did not happen.

**`bge-small` instead of nomic.** Still a local model in every process, and it
changes the stored dimension, so it costs the same migration as this change for
none of the same benefit.

**A quantized nomic.** It cuts the resident cost and keeps everything else: a
model per process, CPU inference on the request path, a cache format to ship,
and a warm-up that has to encode what the cache misses.

**Gating the public-strategy sync behind `EMBEDDING_INDEX_SYNC_ENABLED`.** The
flag is true only on the api, and both callers of `search_example_plans` run
elsewhere - the agent tool in the worker, the MCP tool in `wdk-mcp` - so the gate
would leave that index permanently empty and the semantic ranking dead. The gate
exists to stop two processes racing one warm-up encode; a per-call list has no
warm-up to race.

# What stays

`onnxruntime` stays a dependency. PIGuard is an ONNX model and loads through it;
only the fastembed text model left.

The record manager and the two tables are the MCP unit's, and the embedder is
declared once per unit; see [the embedding index belongs to the MCP
unit](the-embedding-index-belongs-to-the-mcp-unit.md).
