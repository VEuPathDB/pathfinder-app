---
type: Decision
title: A researcher's provider key is sealed under a secret of its own and read by the worker, and every call names its payer
description: A key a researcher enters is checked with one generation request, sealed with AES-256-GCM under PROVIDER_KEY_ENCRYPTION_KEY with the row's user, application and provider as associated data, and opened only by the worker at turn start, by user id. A live key pays for every model of its provider, a refused one pays for nothing and is never replaced by the deployment's key, and each usage row names who paid. Keys in the browser, in the job payload, in the environment or in plaintext, Fernet, sealing to a public key, a secret derived from API_SECRET_KEY, a free models listing as the check, one payer per turn and a table of its own for own-key spend were rejected.
tags: [security, models, quota, persistence, worker, telemetry, settings]
generated: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-24T00:00:00Z }
status: stable
---

# What was decided

**Entry.** `PUT /api/v1/me/provider-keys/{provider}` (`openai`, `anthropic`,
`google`; any other name is a 422) sends one short generation request to the
provider's cheapest catalog model through the construction a turn uses
(`platform/model_keys.py::probe_key`), and stores nothing unless it answers
2xx. A 408, a 429 or a 5xx is `PROVIDER_UNREACHABLE` (503); any other refusal
is `PROVIDER_KEY_REFUSED` (422). A deployment with no key secret answers
`PROVIDER_KEYS_DISABLED` as a 403: the refusal stands until an operator sets
the secret, so it is not an outage a caller may wait out. The route answers the PathFinder application
alone and is rate limited to 10 an hour, because each call spends on the key it
names. No response carries the key: the listing names its last four characters.
The request validation handler logs and answers the place and the reason of a
refused field, never its value.

**At rest.** `user_provider_keys` (migration `2026_09_24_0002`) holds one live
row per user, application and provider. The blob is `0x01 || nonce ||
ciphertext+tag` from `platform/provider_key_cipher.py`; the associated data is
`user_id:application_id:provider`, so a blob copied into another row does not
open. A revoked row keeps its hint and drops its ciphertext, and a CHECK
refuses a ciphertext on a revoked row. The secret is its own setting; empty
turns the feature off, and a value that is not 32 bytes of base64url fails
startup.

**In a turn.** The API process reads key standing only, never a key. The worker
opens the keys by user id when a turn starts (`jobs/turn_keys.py`, for both the
chat turn and the turn a finished durable task opens) and holds them in a
context scope for that turn alone; no job payload, checkpoint, graph state or
chunk carries one. A key the secret no longer opens is marked `unreadable`.

**The payer rule** (`domain/provider_keys.py::KeyStatuses.payer`). For each
provider a turn's roles run on: a live key pays; a refused or unreadable key
refuses the turn (409 at dispatch, a typed turn failure in the worker); else the
deployment pays when it holds the provider's key; else `PROVIDER_NOT_CONFIGURED`
(422). The monthly allowance stops only a turn that runs some model on the
deployment's key. A served tool's cost is always the deployment's.

**Every model is guarded** (`platform/model_keys.py::GuardedModel`), keyed or
not: a provider error reaches the turn as its status with no body, raised
outside the handler so no traceback, log or span carries the provider's text;
OpenAI echoes a key's last four characters in its 401. A refusal of the
researcher's key, read from bodies recorded by
`pathfinder.devtools.provider_refusals`, is raised as the typed refusal, which no
model retry can pass, and marked on the row after the turn.

**Usage.** Each `monthly_usage` row names its payer (runtime `0.3.0a17`). The
quota pill shows the allowance with its bar, or the bare own-key spend when the
researcher holds a live key.

# What was rejected

- **Keys in the browser**, sent with each chat request: the whole body is the
  job payload, so the key would sit in `procrastinate_jobs.args` and the
  worker's start log, the completion turn rebuilds its body without it, and any
  script on the page can read it.
- **Carrying the key in the job payload or the durable job context**, as the
  WDK token travels: it persists in the queue, it needs a log scrub after the
  fact, and the completion turn never sees it.
- **Keys in the environment per deployment**: that is the deployment's own key,
  one variable and a restart per person, and the ledger cannot say who paid.
- **Plaintext behind database permissions**: the api and the worker reach
  Postgres as one role, so every dump and replica would hold live credentials.
- **Fernet**: no associated data, so a ciphertext copied into another row opens.
- **Sealing to a public key the worker alone can open**: both processes read one
  env file today, and the api sees the key at entry anyway.
- **Deriving the seal from `API_SECRET_KEY`**: rotating the session secret would
  destroy every stored key, and one leak would expose both.
- **Checking a key with the free models listing**: it proves authentication
  only; a key with no credit passes and fails on the first turn.
- **One payer per turn**: a stronger model for the reasoning roles on the
  researcher's key beside the deployment's cheaper model is the reason to add
  a key, and every charge already knows its model.
- **A PathFinder table for own-key spend**: it would split one monthly ledger
  across two owners.
- **A regex scrub of log lines for key shapes**: the key reaches no logger by
  construction, a pattern list goes stale, and
  `tests/integration/chat/test_no_key_in_any_sink.py` holds the property.
- **A 503 for a deployment with no key secret**: it tells the caller to retry
  later, and no retry passes a refusal that lasts until an operator acts.
- **Falling back to the deployment key when a researcher's key is refused.**

# Where it lives

`domain/provider_keys.py`, `platform/provider_key_cipher.py`,
`platform/model_keys.py`, `platform/key_refusals.py`,
`persistence/repositories/provider_key.py`, `services/provider_keys.py`,
`jobs/turn_keys.py`, `transport/http/routers/me.py`, and in the web
`features/settings/components/settings/ProviderKeySettings.tsx`,
`lib/models/payers.ts`, `app/components/QuotaPill.tsx`.
