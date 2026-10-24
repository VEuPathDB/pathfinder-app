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
the job hands over to the synthesis; until that exists it stores `synthesized`
with no synthesis.

**One reviewer run.** The prompt is the stored `FindingDetail` as JSON. The
reads a review may cite are `finding:<id>`, `evidence:<id>:<kind>` for each
stored piece of evidence, and the references its own research reads returned.
The output validator retries a review whose verdict or `known_from` names
anything else, whose verdict names a gene the finding's target does not, or
that claims a literature status when no research source was open. A run under
`REVIEW_LIMITS` that stops at its limit, or never answers a valid review, is
stored `undecided` with the reason, so the loop moves on.

**Agreement.** The sample is the first AGREEMENT_SAMPLE of the findings the run
reviews, ordered by `sha256(f"{seed}:{finding_id}")`, so a rebuilt run picks the
same ones. A sampled finding is judged by a second, fresh reviewer run on the
same stored detail, and its verdict kind is stored as `second_verdict` on the
same row in one write, so a job killed between the two runs repeats both and
stores one row.

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
