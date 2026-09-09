---
type: Decision
title: A WDK-backed feature requires a registered VEuPathDB login
description: Every route that reads or writes a user's WDK resources refuses a request that names no registered VEuPathDB user, with 401 WDK_LOGIN_REQUIRED, and refuses one whose token names another account, with 401 WDK_IDENTITY_MISMATCH, except a dev-login session, which is synthetic and acts as its token; guest minting is deleted; the application's service token serves user-independent reads only; a shared guest or service identity for anonymous users was rejected.
tags: [security, auth, veupathdb, wdk, guests, transport]
generated: { by: claude-code/opus-5, at: 2026-08-19T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
status: stable
---

# What was decided

VEuPathDB serves the WDK service to registered users only. Measured on
2026-08-19 against plasmodb.org and toxodb.org: an anonymous
`GET /record-types/transcript/searches/GenesByTaxon` answers **401 "Valid API
Key required for this endpoint."**, the same call carrying a freshly minted
guest `Authorization` cookie answers **403 "This endpoint is only available to
registered users, and requires an API key."**, `POST /users/current/steps` with
that cookie answers 403 as well, and a registered user's token answers **200**.
A browser `User-Agent` and `Referer` change nothing.

So PathFinder requires a registered VEuPathDB login for every WDK-backed
feature. Three rules follow, and they are separate rules.

**One refusal, one code.** `ErrorCode.WDK_LOGIN_REQUIRED` is 401 problem+json,
title "VEuPathDB login required", detail "Sign in to VEuPathDB to use searches,
strategies and gene sets." The frontend keys on the code, not on the prose, so
the wording can improve without breaking the recogniser.

**The gate is on the routes that reach a WDK account, one by one.** Not on a
whole router: a listing that reads local rows keeps working while the create
that materializes a WDK object is refused, so a user who loses their VEuPathDB
access can still see and delete what they already have. `POST
/api/v1/experiments/{id}/threshold-sweep` is gated because it runs the
experiment's search again on WDK; `DELETE /api/v1/gene-sets/{id}` is not,
because it deletes a local row. Two routes whose WDK call is an opt-in flag are ungated on purpose -
`DELETE /api/v1/conversations/{id}?deleteFromWdk=true` and `DELETE
/api/v1/user/data?deleteWdk=true` - because the local half must run for a
signed-out user; their WDK half is skipped and reported instead. The whole
table is pinned by
`tests/unit/transport/test_wdk_gate_route_table.py`, which also carries the
reason for every ungated route that can still reach WDK.

**Chat asks its assistant, and PathFinder's answer is this gate.** `POST
/api/v1/chat` carries no fixed dependency: `resolve_chat_assistant` resolves
the turn's assistant and runs the `identity_gate` that assistant declares, and
PathFinder's spec declares `require_registered_wdk_login`, so the refusal on
that route is the same 401 with the same code, title and detail. An assistant
that declares no requirement is served without one; the application's own
session auth is unchanged, because that is the runtime's, not the assistant's.
Recorded in
[the orchestration belongs to the assistant](the-orchestration-is-the-assistants.md).

**The dependency is where the check lives, not the call site.**
`transport/http/deps.py::require_registered_wdk_identity` reads the token the
request resolver put on `veupathdb_auth_token_ctx` (bearer, `X-VEUPATHDB-AUTH`,
or the `Authorization` cookie) and verifies it locally against the OAuth
server's cached ES512 key, the same validation the bearer path already does. A
missing token, a token that does not verify, and a token whose `is_guest` claim
is true are all the same refusal. An unreadable JWKS stays **503** naming the
identity provider, because the credential was never examined.

**One PathFinder session acts as one VEuPathDB account.** The `pathfinder-auth`
cookie and the `Authorization` cookie are independent, so a second VEuPathDB
sign-in in another tab leaves a session whose two credentials name two accounts.
The gate resolves the token to its internal user through
`services/wdk_identity.py::require_session_matches_wdk_identity` and refuses a
request whose token names another user with 401
`ErrorCode.WDK_IDENTITY_MISMATCH`, title "VEuPathDB account changed". A token
that resolves to nobody is a WDK outage, not a second account, and the session
keeps its own identity. `POST /api/v1/veupathdb/auth/refresh` relinks: it
resolves the token's account on every call, and mints a new internal token when
that account is not the cookie's, instead of returning early on any cookie that
decodes. The web client treats the new code like the login refusal, except that
it calls the refresh once and retries first.

**One exemption: the dev-login session.** The identity match applies to a
session minted from a VEuPathDB identity. `POST /api/v1/dev/login` mints a
synthetic user with no VEuPathDB account, and it mounts only under the mock
overlay, so its session acts as whatever token the request carries. The route
marks its JWT, `platform/security.py::decode_session_token` reads the mark, and
the `Principal` carries `credential="dev-login"` beside `veupathdb-bearer`;
`require_session_matches_wdk_identity` returns early for that credential. The
login refusal is unchanged: a dev-login session still needs a registered,
non-guest token to reach a WDK account. Production cannot mint the credential,
and `tests/unit/transport/test_dev_login_is_test_only.py` pins both halves: the
app built without the overlay carries no dev-login route, and the dev router is
the only caller of `create_dev_login_token`. Without this, every Playwright
worker signs in as `worker-N` and shares one registered VEuPathDB test account,
so the gate answers 401 `WDK_IDENTITY_MISMATCH` on every WDK-backed route.

**The service account is the application, never a user.** `VEUPATHDB_AUTH_TOKEN`
is the fallback in `veupathdb/wdk/_http.py`, and it may serve only
user-independent reads: record types, searches, parameter metadata and
vocabularies, catalog warmup and semantic-index builds. The transport enforces
it rather than trusting call sites: a request whose path starts `/users/` and
whose `veupathdb_auth_token_ctx` is empty raises `WDK_LOGIN_REQUIRED` before
anything leaves the process. `/users/current` is included, because it resolves
which WDK account the caller is, and without a token the answer is the
application's own account or a fresh guest - neither of which may own the
caller's work.

# What was deleted

Guest minting, in full. `auth_login.py::mint_guest_token`,
`extract_any_auth_cookie`, `services/wdk_identity.py::ensure_wdk_identity`, the
`users.wdk_guest_token` column and its repository setter are gone, with an
alembic revision dropping the column. Nothing in the product mints a WDK
identity any more; the user brings one or the request is refused.

`veupathdb-py: src/veupathdb/wdk/current_user.py::fetch_current_user` also
returns `None` when the request
carries no token. It reads `GET /users/current`, and with the service account
configured it would otherwise report the **application's** account as the
signed-in user on `GET /api/v1/veupathdb/auth/status`.

# The rejected alternative: one shared identity for anonymous users

Keep guest mode working by sending the service account (or one shared
registered account) for users who are not logged in. It is refused for reasons
that are not stylistic:

- Every strategy, step and dataset those users create would land in **one**
  VEuPathDB account, so each user would see, edit and delete the others' work.
  PathFinder acts on WDK **as** the user
  ([bearer identity and service tokens](bearer-identity-and-service-tokens.md));
  it does not answer questions about WDK from a shared store.
- The researcher would never find the work again. A strategy built in
  PathFinder is meant to open on the VEuPathDB website under the researcher's
  own login, which is the whole point of pushing it there.
- It hands PathFinder's own credential the blast radius of every user's
  mistakes, with no per-user attribution on VEuPathDB's side.

Also rejected: keeping a per-user persisted guest token as a fallback for
whoever cannot log in. VEuPathDB refuses guest tokens on these endpoints today,
so the fallback is a stored value that cannot work, and a fallback that fails
later is worse than a refusal that names the fix.

# What a caller sees now

A user with no VEuPathDB session can still hold conversations, notes, memories
and settings, list and delete their own gene sets, read and annotate their own
experiments, and purge their own data. Chat, searches, strategies, step counts,
gene-set creation and enrichment, experiment runs and results, and the eval
routes answer 401 `WDK_LOGIN_REQUIRED` until they sign in.

A user who signs in to VEuPathDB as a second account sees those same routes
answer 401 `WDK_IDENTITY_MISMATCH` until the session is relinked, instead of
writing analyses and strategies under an account the session cannot read back.
