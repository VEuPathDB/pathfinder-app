---
type: Decision
title: Upstream is the falsifier, which is why WDK reference material is admissible
description: The bundle bans reference docs because they rot. WDK reference is the exception, because WDK's source and live API can prove it wrong.
tags: [wdk-alignment, documentation, okf, meta]
generated: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-10T00:00:00Z }
status: stable
---

# The conflict

Before this decision the bundle admitted Decisions, Backlog items and Conventions, and
excluded "anything the code, tests, or type signatures already say". A WDK reference is
exactly the kind of document that exclusion was written to keep out. Reference docs rot,
and a wrong doc is worse than a missing one because it gets believed.

# Why WDK is the exception

Every other candidate for reference material describes PathFinder, and PathFinder's own
code is the better description of PathFinder. WDK is different: it is a system we do not
control, whose behavior we must match exactly, and whose truth lives in someone else's
repository. Reading our code tells you what we do. It cannot tell you whether what we do
is correct.

So the oracle is external. WDK's Java source, `wdk-client`'s TypeScript, ApiCommonModel's
XML and the live REST API decide whether a WDK statement is true. That makes a WDK rule
falsifiable, which is the bundle's actual requirement, and it makes staleness detectable
rather than a matter of opinion.

# What was rejected

**Leave WDK knowledge where it already is.** It is not hidden. Take the JSESSIONID
silent-zero, where a process query without a Tomcat session cookie returns zero results
instead of an error. It was written down in at least six places: a Key Technical Note in
`CLAUDE.md`, two docstrings in `veupathdb/wdk/_http.py` (`_init_wdk_session` and
`close`), a design dropdown in the api Sphinx page for the integrations (since deleted), the `silent_zero`
anomaly in `devtools/diagnosis.py`, and its row in `devtools/README.md`.

This document originally said "each of those is true". It should not have, because nothing
in the repository had ever checked, and the first time anyone did, the claim did not
reproduce.

Building the bundle meant sourcing that claim before writing it as a rule. On 2026-08-10,
`POST /record-types/transcript/searches/GenesByOrthologPattern/reports/standard` against
plasmodb.org:

| Request | `profile_pattern` | `totalCount` |
|---|---|---|
| No cookies at all | `%hsap:N%pfal:Y%` | a large result |
| No cookies at all | `%ggor:N%hsap:N%mmus:N%pfal:Y%` | 3337 |
| Cookie jar seeded by `GET /plasmo/app`, which sets `JSESSIONID` | `%ggor:N%hsap:N%mmus:N%pfal:Y%` | 3337 |

A cookie-less process query returned a full result set, and the identical query carrying a
session cookie returned the same count. WDK's source points the same way at the pinned
sha: [`TemporaryUserDataStore`](https://github.com/VEuPathDB/WDK/blob/e534d2e6a5119165e1742c7a9e07a371217ddda5/Model/src/main/java/org/gusdb/wdk/cache/TemporaryUserDataStore.java#L16-L23)
is keyed by user id, its class comment says the data used to live in the session object
and no longer does, and no `HttpSession` appears anywhere in the service layer.

Be precise about what that shows. One process query, on one site, on one day, did not
reproduce. That is not proof the behavior never occurred, on another site or against an
older deployment, and it is not an argument for deleting the workaround. It is proof that
nobody could tell either way, which is the point.

There is a mechanism that produces the same observable signature and that did verify:
`WDK-AUTH-001` (`veupathdb-py: docs/knowledge/wdk/rules/auth-and-transport.md`). A request with no `Authorization`
credential is not rejected; WDK mints a brand new guest user for it. Three consecutive
unauthenticated `GET /users/current` calls returned three different user ids, and the same
three sharing a cookie jar returned one. A client that drops its token is a stream of
strangers, so strategies list empty, steps 404, and any flow spanning several requests
produces exactly the "well-formed request, 200 response, empty answer" shape the JSESSIONID
note describes. PathFinder's `JSESSIONID` handling and its `Authorization` handling were
written in the same period, so a fix credited to one may have been delivered by the other.

**This makes the case for the bundle stronger, not weaker.** The thesis was that scattered,
unpinned knowledge cannot be checked. The example chosen to illustrate the thesis turned
out to be an instance of it. Six statements, not one; none citing a line of WDK; one of
them in the file that loads every session; and no mechanism anywhere in the repository
capable of raising a hand. Each of the six failed in its own way:

- **They do not assert with equal force, and nothing reconciles them.** `CLAUDE.md` states
  it flatly: process queries "silently return 0 without JSESSIONID". `devtools/README.md`
  hedges it to one of two possible causes, alongside "wrong params". The reST page
  describes `JSESSIONID` purely as the auth cookie mechanism and never mentions the silent
  zero at all. A reader gets a different confidence level depending on which file they
  happen to open, and no file knows the others exist.
- **The test pins us, not WDK.** `veupathdb-py: tests/unit/wdk/test_http.py`
  asserts that our client re-initializes the session when the token changes. That is our
  conformance, and it passed on every commit throughout, including every commit for which
  the upstream behavior it exists for may not have been happening at all. No test asserts
  that upstream behavior, and no test could: it is WDK's, not ours.
- **Nothing is pinned.** Not one of the six cites a line of WDK, and the cost of that is
  worse than the original wording allowed. Unpinned knowledge cannot tell you which
  statement went stale when WDK changed. It also cannot tell you whether the statement was
  ever true. Both questions stayed unanswerable for as long as the claim sat in six
  unpinned places.

That is the actual failure: not that the knowledge is missing, but that as a body it is
unlocatable and unverifiable. Scattering is what a pinned, gated bundle fixes, and the
first thing the bundle did was falsify its own motivating example. The claim now lives in
one place, `veupathdb-py: docs/knowledge/wdk/rest/transport-quirks.md`, recorded as an
open question with its evidence attached rather than as a rule, because a rule here must be
sourceable and this one is not.

**Put it in `CLAUDE.md`.** A one-line summary already lives there, and one line is the
right size for a file that loads every session. The full material is not: WDK's parameter
system alone is larger than the whole of `CLAUDE.md` today, and it is needed rarely.
Paying that context cost on every unrelated turn is the wrong trade. `CLAUDE.md` keeps
the reminder; the bundle carries the evidence.

# The condition attached

The exception is narrow, and it is enforced rather than promised. A WDK rule carries
upstream evidence pinned to a commit sha, a PathFinder anchor, and a conformance status.
`scripts/check-wdk-rules.mjs` fails the build on an unpinned citation, a moved anchor, or
a named test that no longer exists. Without that script this decision would be an
optimistic one; with it, a rule that has gone stale is a red build.

# Anchor

`scripts/check-wdk-rules.mjs` and its fixture suite `scripts/check-wdk-rules.test.mjs`,
which asserts each failure mode independently. The convention it implements is in
[conventions/maintaining-this-bundle.md](../conventions/maintaining-this-bundle.md).

The live evidence above is itself falsifiable and unpinned by nature: it is a request, not
a line of source. Both checks are written out in full in
`veupathdb-py: docs/knowledge/wdk/rest/transport-quirks.md` so anyone can repeat them,
and both are anonymous, so repeating them needs no credential. A reproduction of the
silent zero would overturn this section, which is the outcome this document wants.
