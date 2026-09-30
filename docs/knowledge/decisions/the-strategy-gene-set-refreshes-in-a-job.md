---
type: Decision
title: The strategy's gene set refreshes in a job
description: A write that moves the strategy's root defers one procrastinate job per thread, and the edit answers as soon as WDK holds it. The job reads the stored root when it runs and skips a set that already holds that root's answer. Reading the genes inside the request, skipping the read only when the tree is unchanged, and taking the lock the thread's turns take were rejected.
tags: [strategy-graph, gene-sets, jobs, wdk]
generated: { by: claude-code/opus-5, at: 2026-09-29T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-29T00:00:00Z }
status: stable
---

# What was decided

**The set auto-import made follows the root in a job, not in the request.**
`services/strategies/gene_set_refresh.py::defer_the_gene_set_refresh` defers the
job `strategy:refresh_gene_set` on the `default` queue after a write that moves
the root: a commit whose `answer_revision` changes, a build, a site edit taken
into the thread, and a count refresh that took one. The job carries the
researcher's WDK token through the same `durable_job_context()` seam the
durable tools use, and the worker runs it (`jobs/tasks.py`,
`jobs/impls/gene_set_refresh_impl.py`).

**One job per thread, apart from the thread's turns.** The job takes
`lock=gene-set-refresh:<conversation id>` and the same `queueing_lock`, so the
refreshes of one thread run one at a time, and a second write while one job
waits queues nothing: the waiting job reads the root when it runs. A chat turn
takes `lock=<conversation id>`, so a turn never waits behind a refresh.

**The worker writes the set and every process reads it from the database.**
`GeneSetStore` holds no per-process copy: every read and write goes to
`gene_sets`, so the api reads the genes the worker wrote. A rename and a VDI
publication write only their own column, so they cannot write older genes back.

**A late job cannot write an older answer.** The job reads the stored strategy
under the thread's strategy write lock, then reads the genes from WDK, then
writes them with the answer revision it read first. A write that lands between
the two reads defers a new job, because the running job no longer holds the
queueing lock. `domain/strategy/revision.py::answer_revision` fingerprints the
root's inputs only (searches, parameters, operators, shape), so a rename or a
step not yet combined moves nothing.

**A set that holds the root's answer is not read again.** `GeneSet.answer_revision`
(column `gene_sets.answer_revision`) names the stored root the genes were read
from; the import records it too, so the first job after a build reads nothing.

**A WDK failure ends the job.** The refresh logs the failure with its duration
and returns; the set keeps its genes and its old revision, so the next write
that moves the root reads again. No task in `jobs/` sets a procrastinate
`retry`, and neither does this one: a failed refresh is not retried by the queue.

# What was rejected

**Reading the genes inside the request.** The refresh reads every gene id of the
root through one WDK standard report. On a vectorbase UNION root of 4456 genes
that took 29.6 s for a rename, 28.9 s for an operator change and about 94 s
(two WDK retries, then a failure) for an added step, while the edit itself
reached WDK in under a second. The canvas stayed in "saving" for the whole read.

**Skipping the read when the pushed tree is unchanged.** Correct as far as it
goes, since a rename writes only a step name, but an operator change and an
added step change the answer and would still wait 29 to 94 s.

**The job takes the thread's lock.** The refresh would never run beside a turn,
but a turn sent right after a canvas edit waits behind the refresh: on a
vectorbase root of 4456 genes the job took 29.81 s and 31.25 s. The refresh
writes only the gene set, and the answer revision already keeps a late job
from writing an older answer, so the turn's lock protects nothing.
