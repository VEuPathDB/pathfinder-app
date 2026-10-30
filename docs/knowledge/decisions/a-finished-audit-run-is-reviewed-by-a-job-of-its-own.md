---
type: Decision
title: A finished audit run is reviewed by a job of its own, one finding at a time, paid like a chat turn
description: When an audit run finishes, `services/audit/job.py` queues `audit:review` on the `audit` queue under the run's lock. The job reviews the run's confirmed findings that name an error, highest impact first, at most MAX_REVIEWS_PER_RUN, one bounded reviewer run each, and stores each review on its own `audit_verdicts` row before the next starts. A seeded sample of AGREEMENT_SAMPLE findings is judged a second time by a fresh run that sees no first answer. The owner's keys pay, the monthly budget and a refused key stop the job with the reason on the run, the research source is screened and metered as a turn's, and the periodic resume pass queues a review whose job was lost. Reviewing inside the audit job, a durable tool the model calls and one reviewer run over every finding were rejected.
tags: [audit, jobs, review, billing, screening]
generated: { by: claude-code/opus-5, at: 2026-10-24T00:00:00Z }
status: stable
---

# What was decided

**The job.** `_set_status(run_id, "finished")` in `services/audit/job.py` calls
`services/audit/reviews.py::defer_review`, which stores
`ReviewProgress(status="waiting")` on the run and defers `audit:review` with
`lock` and `queueing_lock` both `audit-run:<run_id>`. The review job and the
audit job of a run therefore never run together, and `start_run` starts no
retry while a review is queued or doing, as the run view already offers no
retry while reviews run. The job body is `jobs/impls/audit_review_impl.py`; the
loop is `ai/audit/review.py::review_until_done`, because a service may not
import `pydantic_ai`.

**What is reviewed.** The confirmed findings that name an error type and have
no review, highest stored impact first, until the run holds
MAX_REVIEWS_PER_RUN reviews (`services/audit/reviews.py::next_unreviewed`).
A finding's review is one row, so a finding is never reviewed twice: a retried
run reviews only its new findings, and a run already `synthesized` with nothing
left defers nothing (`start_review`). The progress (`done`, `total`, the status
and a message) is on `audit_runs.review` after every review. With nothing left
the job writes the run's synthesis and then stores `synthesized`.

**The synthesis.** `ai/audit/synthesis.py::synthesize` reads the run view, the
stored reviews and the stored impacts, and one bounded run under
`SYNTHESIS_LIMITS` writes a `SynthesisDraft`: one section per error type with
its cause and how the checks confirmed it, the headline finding ids and a
summary. The code attaches `agreement=review_agreement(<the stored reviews>)`;
the model never writes it, so no rate rests on one judgement. The output
validator retries a draft that names a finding no review keeps as an `error`, a
section whose findings' reviews name another error type, a headline out of
descending impact (the review's impact when set, else the stored one, a
finding with none last), or a summary that writes a number. The summary
writes no number at all: the run shows the kept, rejected and undecided counts,
the genomes and the agreement beside it, so a share of kept findings has no
place in it, and the summary is stored as written (`Synthesis`). With no kept
finding the job makes no model call, reads no budget, and stores
`NO_FINDING_KEPT` with no section. `AuditReviewRepository.reopen_review` sets
the review to waiting and clears the run's synthesis in one write; a review pass
(`defer_review`), a finished run and a retry that reopens a finished run all
call it, so a pass that stops never shows an earlier synthesis beside its state. A synthesis that spends its retries or its limit
stores none and stops the review with `SYNTHESIS_STOPPED`; a used budget stops
it before the call; a later start reruns only the synthesis. The run is
charged in a `finally`, like a reviewer run, so a provider error after paid
requests is charged once.

**What the report reads.** `services/audit/review_views.py` states the stored
reviews and the synthesis in the words of `domain/audit/words.py`. Each finding
on a page carries its `review_line` and the finding detail its `review_text`;
a finding read joins its review row, so `reviewed` is `review is not None` and
the page reads both in one query. The run view carries `error_types`, one per
error type its findings name, in `ERROR_TYPE_TITLES` order, with the count,
the model genomes, the highest certainty and, from the synthesis section, the
cause, how it was confirmed and its findings. A review supersedes the stored
type: each finding counts once, under the error type and certainty of the
review that names one, and under the stored ones otherwise
(`AuditTallyRepository.error_type_tally`). A finding the review rejects
(`no_error`) is left out of the counts, genomes and certainty; an undecided one
stays under its stored type. Its line still shows the review. A finding line shows the error type and certainty
of the review that keeps it, and the stored ones otherwise, and whether its two
reviews disagree (`reviewsDisagree`, with `disagreementText` naming both
verdicts), read from the stored review row and never from the synthesis prose.
A finding whose reviews disagree may stay in a section and in the headline,
because every line of both carries the disagreement; `headline`;
`review_state`; `agreement`, the synthesis's or else the one the stored
reviews give, with its sentence; and `disputed`, the line of each finding whose
two reviews disagree, also one no section names. A reply that reads a run fact
names each disputed finding (`domain/dispute_references.py`). A synthesis
section counts its findings (`count`, the length of `findingIds`), and its
cause and what confirms it write no number. A finding's reviewed impact is shown beside
the stored impact, which keeps the page order. No share of kept findings is
shown.

**One reviewer run.** The prompt is the stored `FindingDetail` as JSON, less its
`models`: the review judges from the facts and the evidence, and the stored
confirmation already holds the spans the figure draws. The
reads a review may cite are `finding:<id>`, `evidence:<id>:<kind>` for each
stored piece of evidence, and the references its own research reads returned.
The output validator retries a review whose verdict or `known_from` names
anything else, or whose verdict names a gene the finding's target does not.
A review with no research source open is offered no literature field and no
literature instruction: its output type is `UnsearchedReview`, which fixes
`already_known` to `not_searched` and refuses a literature status sent anyway.
A run under `REVIEW_LIMITS` that stops at its limit, or spends its retries, is
stored as a stopped review (`FindingReview.stopped`, verdict `undecided`, the
cause in its text), so the loop moves on and a stopped review is never read as
a judgement. A run that spends its retries stores the last refusal in plain
words after `OUT_OF_RETRIES`: each field that failed with its message, or the
validator's words.
The reviewer runs on the review role's model settings, its reasoning effort
included, as the auditor runs on its own.

**Agreement.** The sample is the first AGREEMENT_SAMPLE of the findings the run
reviews, ordered by `sha256(f"{seed}:{finding_id}")`, so a rebuilt run picks the
same ones; a retried run fills only the places its earlier pairs left, so the
pairs of a run never pass AGREEMENT_SAMPLE. A sampled finding is judged by a
second, fresh reviewer run on the same stored detail, and its verdict kind is
stored as `second_verdict` on the same row in one write, so a job killed between
the two runs repeats both and stores one row. A stopped run of either side
leaves no second verdict, so the agreement counts only two judgements.

**Payment.** `services/turn_payment.py::turn_payment` holds the rule
`require_turn_paid` answers a chat request with: who pays for each provider,
and the monthly budget when the deployment pays and the limit is reached. The
job runs under the owner's keyring. A refused or missing key stops it with the
error's title; a used budget stops it with "the monthly budget is used" before
the next review. Each reviewer run is charged on the row of its payer.

**Literature.** The job opens the research source through
`ai/capabilities/screened_sources.py`, the same helper the turn runner uses:
the deployment's credential, the injection judge on every result and the
metered toolset. A result the judge flags reaches the reviewer as the withheld
sentence. A deployment that admits no research server gives `not_searched`.

**Failure.** A job that raises anything else stores `stopped` with "the review
job failed: <error type>" and the true counts, and the tokens its runs spent are
charged. A stopped review is not pending, so the resume pass does not call the
provider again; `review_audit_run` resumes it when the researcher asks. The
status `finished` and the progress `waiting` are written in one transaction, and
a deferral that fails is logged and left to the resume pass, so a finished run
is never halted by its review.

**Resume.** The job stops after `units.SLICE_SECONDS` of work and queues its
continuation. `maintenance:resume_stranded_audits` also queues a review for
every finished run whose review is `waiting` or `reviewing` and has no job
queued or doing (`AuditReviewRepository.pending_reviews`), so a job the
stalled-job sweep failed continues at the next unreviewed finding.

# What was rejected

**Reviewing inside the audit job.** The audit job runs signed in as the owner
and erases the sign-in at finish; a review reads no site. Model spend would sit
inside the site job's slice and its failure handling, and a refused key would
halt the run itself.

**A durable tool the model calls.** It takes the thread's lock, so the thread
waits behind up to fifty model runs, and the review would only start when a
model chose to call it.

**One reviewer run over every finding.** One context holding fifty findings
and their evidence costs more per finding, lets one finding's evidence leak into
another's verdict, and loses every review when it fails.

# Anchor

`apps/api/src/pathfinder/services/audit/reviews.py`,
`apps/api/src/pathfinder/services/turn_payment.py`,
`apps/api/src/pathfinder/ai/audit/review.py`,
`apps/api/src/pathfinder/ai/capabilities/screened_sources.py`,
`apps/api/src/pathfinder/jobs/impls/audit_review_impl.py`,
`apps/api/src/pathfinder/tests/integration/jobs/test_audit_review_job.py`,
`apps/api/src/pathfinder/tests/integration/jobs/test_audit_review_resume.py`.
