---
type: Decision
title: A VEuPathDB bearer token is the user; a service token is the application
description: PathFinder verifies VEuPathDB's own ES512 bearer JWT against the OAuth server's JWKS to name the user, and reads a separate service-token header to name the calling application; proxied-user-id was rejected because PathFinder must act on WDK as the user and therefore needs the user's own token.
tags: [security, auth, veupathdb, oauth, transport, tenancy]
generated: { by: claude-code/opus-5, at: 2026-08-19T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-19T00:00:00Z }
status: stable
---

# What was decided

Two identities travel on a request, and they are not the same question.

**Who the user is** comes from one of three credentials, read in this order by
`platform/security.py::_identify`:

1. `Authorization: Bearer <token>` that verifies as a PathFinder HS256 JWT -> `pathfinder-bearer`.
2. The same header otherwise read as a VEuPathDB token -> `veupathdb-bearer`.
3. The `pathfinder-auth` cookie -> `pathfinder-cookie`.

Nothing else authenticates; a request with none of them is 401. The order
matters: PathFinder's own token is checked first, so a locally minted token
never costs a network call to the OAuth server.

**Which application is calling** comes from the optional
`X-PathFinder-Service-Token` header, matched in constant time against
`PATHFINDER_SERVICE_TOKENS` (`app_id:secret[,app_id:secret...]`, each secret at
least 32 characters, parsed and validated when settings load). A valid token
sets `Principal.application_id`; an unknown one is 401; an absent one leaves the
default `pathfinder`. There is no applications table and no per-application
routing: the tenancy work decides both.

# The protocol, and where it is written down

VEuPathDB's own services validate a bearer token with
`OAuthClient.getValidatedEcdsaSignedToken(oauthUrl, token)`. Reading that method
and the server that mints the keys settles every open question:

- The key comes from `GET <OAUTH_URL>/jwks`
  ([`OAuthClient.java` L134-160](https://raw.githubusercontent.com/VEuPathDB/OAuth2Server/master/Client/src/main/java/org/gusdb/oauth2/client/OAuthClient.java),
  [`Endpoints.java` L7](https://raw.githubusercontent.com/VEuPathDB/OAuth2Server/master/Client/src/main/java/org/gusdb/oauth2/client/Endpoints.java)).
  The client takes the first key whose `kty` is `EC` (L162-173) and caches it for
  120 seconds (L78).
- The algorithm is **ES512** on **P-521**
  ([`Signatures.java` L32](https://raw.githubusercontent.com/VEuPathDB/OAuth2Server/master/Client/src/main/java/org/gusdb/oauth2/shared/Signatures.java);
  the JWKS entry it publishes at L130-142 carries `alg: ES512`, `crv: P-521`,
  `x`, `y` and a non-standard `k` holding the same key as base64 X.509).
- Claims: `sub` is the user id and `is_guest` says whether the user is
  registered ([`ValidatedToken.java` L44-50](https://raw.githubusercontent.com/VEuPathDB/OAuth2Server/master/Client/src/main/java/org/gusdb/oauth2/client/ValidatedToken.java));
  the full set is [`IdTokenFields.java`](https://raw.githubusercontent.com/VEuPathDB/OAuth2Server/master/Client/src/main/java/org/gusdb/oauth2/shared/IdTokenFields.java).
- **Issuer and audience are not checked.** `validateClaims` is an empty method
  with a TODO (`OAuthClient.java` L386-390). PathFinder does the same, and the
  reason is not laziness: a site mints its tokens for its own client id, so a
  token PathFinder receives from a browser session carries the website's `aud`,
  not PathFinder's. Expiry is enforced, because the JWT library enforces it.

Measured against the live server: `https://auth.veupathdb.org/jwks` publishes
exactly two keys, `kty: oct` with the literal placeholder `k:
"<your_client_secret>"` and `kty: EC` with `alg: ES512`, `crv: P-521`. A real
registered-user token has the header `{"alg":"ES512"}` with **no `kid`**, so a
key lookup by key id finds nothing and the `kty == "EC"` rule is the only one
that works. Its payload carries `sub`, `is_guest`, `iss`, `aud`, `azp`, `iat`,
`auth_time`, `exp`, `jti`, `preferred_username` and `signature` - and **no
`email`**.

# Why the internal user still costs a WDK call

`users.external_id` is the email, because that is what the cookie login flow
stores. The bearer token does not carry one. So the bearer path resolves the
email through the same function the refresh route uses
(`veupathdb-py: src/veupathdb/wdk/current_user.py::resolve_registered_email`
-> WDK `GET /users/current`), and bearer and cookie therefore land on the same row instead
of two rows for one person. The mapping is remembered per token hash for five
minutes so a bearer client does not pay a WDK round trip on every request.

Guest tokens are refused on the bearer path. A guest is a new identity per
uncredentialed request (WDK-AUTH-001, `veupathdb-py: docs/knowledge/wdk/rules/auth-and-transport.md`), so
it names nobody durable to own conversations and memories. The cookie flow
refuses them too now: every WDK-backed route requires a registered login, and
the persisted per-user guest token is deleted
([a WDK-backed feature requires a registered VEuPathDB login](wdk-requires-registered-login.md)).

# The rejected alternative: proxied-user-id

`lib-jaxrs-container-core` lets a service act as another user by sending
`proxied-user-id`
([`AuthFilter.java` L224-255](https://raw.githubusercontent.com/VEuPathDB/lib-jaxrs-container-core/master/src/main/java/org/veupathdb/lib/container/jaxrs/server/middleware/AuthFilter.java),
[`RequestKeys.java` L8-13](https://raw.githubusercontent.com/VEuPathDB/lib-jaxrs-container-core/master/src/main/java/org/veupathdb/lib/container/jaxrs/utils/RequestKeys.java)).
It is not adopted, for two reasons that are both fatal here:

- The header is honoured **only** beside a valid `admin-token` that matches the
  service's configured `ADMIN_AUTH_TOKEN`, on a resource annotated to allow the
  override (`AuthFilter.java` L73-114). It is an admin facility, not a
  service-to-service identity.
- PathFinder does not answer questions about WDK; it **acts on WDK as the
  user**, creating strategies and steps the user then owns in their own account.
  That needs the user's own token on the outbound request, which is exactly what
  the bearer path already supplies. A proxied id would let a caller name a user
  without holding that user's credential, and PathFinder would then have no
  token to act with.

Also rejected: adding an `email` claim requirement, which would make PathFinder
depend on a claim the live token does not have; and validating `aud` against a
configured client id, which would refuse every browser-session token. The client
id setting is deleted rather than left unread, so nothing suggests otherwise.

# An unreadable key is not a bad token

A JWKS that cannot be read - the OAuth server is unreachable, answers non-200,
or publishes no EC key - is **503** naming the identity provider, not 401. A 401
would tell a caller its credential is wrong when the credential was never
examined, and a client that retries on 503 and re-authenticates on 401 would
take the wrong action. A token that fails against a key we did hold stays 401.

# The CSRF consequence

`X-Requested-With` is still required on every state-changing request that is not
carrying a bearer token. CSRF is a cookie threat: a forged cross-origin request
rides the browser's cookie jar, and a browser never attaches an `Authorization`
header by itself. So a bearer request is exempt and a cookie request is not,
which is what makes the header usable by a non-browser caller at all.
