---
type: Decision
title: The strategy's gene set refreshes in a job
description: A write that moves the strategy's root defers one procrastinate job per thread, and the edit answers as soon as WDK holds it. The job reads the stored root when it runs and skips a set that already holds that root's answer. A root the refresh refuses (above the cap, of records that are not genes, or with no genes) leaves the genes and marks the set out of date with why. Reading the genes inside the request, skipping the read only when the tree is unchanged, and taking the lock the thread's turns take were rejected.
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

**A refused root marks the set out of date.** The refresh refuses a root in three
ways, and each keeps the set's genes and its old revision:
- the root holds more records than `STEP_GENES_CAP`, refused before any answer is read
  (`above_the_cap`, with the count and the cap);
- the root holds records that are not genes, such as ortholog groups (`not_genes`, with
  the record class);
- the root returns no genes (`no_genes`).

`GeneSetService.resync_strategy` records the reason on the set (`GeneSet.out_of_date`,
column `gene_sets.out_of_date`, one model discriminated by `kind`), and the next take
that returns genes clears it. The mark is written alone (`GeneSetStore.set_out_of_date`,
an UPDATE like the name and the VDI pointer), so a rename in the window stands and a set
deleted in the window stays deleted. A set out of date is read again even when the root goes
back to the revision it holds. The API returns the record as `outOfDate`, and the
gene-set listing in the thread marks the set "Out of date" with the reason in plain words.
An export of a set out of date says so in its notice.

**Every thread without a set takes the import at its next write.** The rule is general:
a thread that has a WDK strategy, links no set and has the latch off takes the automatic
import in the refresh job after the next write that moves the root. That covers a build
above the cap, a root of records that are not genes, a failed import, a strategy built on
the canvas, a strategy imported from WDK and a fork, which starts with the latch off so
that the branch imports its own set. Such a thread gains a set in the researcher's library
once its root returns genes within the cap. A thread whose researcher deleted the set
keeps the latch on and is never imported again.

`import_gene_set_for_conversation` holds `gene-set-import:<conversation id>` for its
transaction, so the build's own import and the job's import of one thread run one at a
time and save one set. The WDK read comes first; the link is then written under
`strategy:<conversation id>`, in one short transaction that also reads the thread's name,
so a rename made during the read names the set.

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
