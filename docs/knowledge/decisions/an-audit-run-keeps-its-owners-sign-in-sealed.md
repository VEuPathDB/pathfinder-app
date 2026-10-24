---
type: Decision
title: An audit run keeps its owner's sign-in sealed on the run, and erases it when the run stops working
description: The run owner's registered VEuPathDB token is checked before the run is sealed, given a deadline or queued (a refused start stores only "sign-in needed"), sealed on audit_runs.sealed_token under PROVIDER_KEY_ENCRYPTION_KEY with the run and its owner as associated data, opened and checked again by every job before its first read, and erased when the run finishes, halts or its job fails; a purge deletes it with the run, and a deployment with no secret refuses every audit as AUDITS_DISABLED. A 401 halts the run, and a 403 halts it only when the kept token no longer holds or after three from units read one after another in one job. Carrying the token in the job, plaintext or sealed, and running a job only while the researcher is signed in were rejected.
tags: [audit, security, jobs, wdk, persistence, purge]
generated: { by: claude-code/opus-5, at: 2026-10-22T00:00:00Z }
status: stable
---

# What was decided

**Why a run keeps a token at all.** A gene report and a gene record need a
registered VEuPathDB login
([A WDK-backed feature requires a registered VEuPathDB login](wdk-requires-registered-login.md)),
the deployment holds no account of its own, and a run reads for hours in jobs
that start long after the request that started it, including one the
periodic resume pass queues. Each job therefore needs the owner's token.

**At rest.** `start_run` reads the caller's token first. It refuses one that
is missing, a guest's or not valid (`require_registered_wdk_login`) and stores
only "sign-in needed" on the run. It seals the token, records a deadline and
queues a job only after the check passes. The seal is on
`audit_runs.sealed_token`, with the provider-key cipher
(`platform/provider_key_cipher.py`). The associated data is
`audit-run:<run_id>:<user_id>`, so a blob copied into another run does not
open. A deployment whose `PROVIDER_KEY_ENCRYPTION_KEY` is empty refuses a
signed-in start with `AUDITS_DISABLED` (403, "Audits are off") and writes
nothing: the refusal stands until an operator sets the secret, as for provider keys
([A researcher's key is sealed and read in the worker](a-researchers-key-is-sealed-and-read-in-the-worker.md)).

**In a job.** Each job opens the token, sets it as the job's VEuPathDB
credential and checks it again before its first read, so a token that expired
during a wait halts the run with no request. A check the OAuth server does not
answer (a transport error or a 5xx) is a wait, not a refusal: the job keeps the
token and schedules its continuation after a pause that doubles from 30 seconds
to 15 minutes. A pause that would pass the deadline ends at it, and a job that
starts past the deadline reads nothing: its stages store their open units
unread. A refused start erases a kept token and
halts the run, but leaves a finished run as it was.

**When the token is erased.** It is set to null when the run finishes, when
the run halts for its sign-in, and when a job raises. A purge
(`DELETE /api/v1/user/data`) deletes the run and the token with it; deleting
the user deletes both too. Deleting the conversation keeps the run: it goes on
under its sealed token until it finishes or halts, its owner still reads it at
`/api/v1/audits`, and neither a thread nor its page can start it again: the
page's `POST /api/v1/audits/{run_id}/start` refuses it with 409
`AUDIT_NOT_STARTABLE`.

**What a refused read means.** A 401 on any read halts the run. A 403 halts it
when the kept token no longer holds when read locally (expired, a guest's, or
not a token at all); with a token that holds, a single 403 is a refusal of that
unit, which settles `failed` with the site's message. Three 403s from three
units read one after another in one job halt the run, because a site that
refuses every read has revoked the sign-in. Any other result between them,
an answer or another failure, starts the count again, and so does a new job.
The halt reopens every failed unit of the run whose message is one of those
403s, and the stages from the first that holds one, as a retry does, so a
refused unit of a stage that had finished is read again; the unit still
`trying` goes back to open. A halt
returns the `trying` units to open without counting a stop, stores
"sign-in needed" on the run and the stage, and erases the token. A new start
with a valid sign-in seals the new token and resumes from the first unfinished
stage.

# What was rejected

**The token in the job's arguments**, as a durable tool carries it. The
runtime's job state reveals the token when it is serialized, so it sits in
plain text in the queue's rows, and every continuation of a run copies it into
one more row. A purge deletes the run's rows but reaches no job row, so the
token outlives the data it was kept to read.

**A sealed token in the job's arguments.** It closes the plain text, and keeps
the other two faults: one copy per continuation, none of which a purge or a
finished run can erase.

**Reading only while the researcher is signed in.** A wait for a site lasts up
to the run's deadline, and a run whose job was lost is queued again by the
periodic resume pass, with no request to take a token from. The run would stop at the
first wait that outlives the researcher's session.

**Any 403 halts the run.** A 403 that lasts on one unit while the sign-in is
valid would halt the run at every start, ask for a sign-in that already holds,
and never read the other units. A halt counts no stop, so the stop cap would
never end it, and the run would never finish.

**Only the token's own claims decide.** A token revoked on the site before it
expires still holds locally, and every read would then settle `failed`. The
count of 403s in a row closes that case without a request to the site.

# Anchor

`apps/api/src/pathfinder/services/audit/sign_in.py`,
`apps/api/src/pathfinder/services/audit/job.py`,
`apps/api/src/pathfinder/services/audit/units.py`,
`apps/api/src/pathfinder/persistence/repositories/audit.py`,
`apps/api/src/pathfinder/tests/integration/jobs/test_audit_run_waits_and_sign_in.py`.
