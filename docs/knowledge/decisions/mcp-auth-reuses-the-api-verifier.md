---
type: Decision
title: The MCP server verifies with the client library's bearer verifier, and publishes RFC 9728
description: veupathdb-wdk-mcp reuses the client library's ES512 verifier for the VEuPathDB token, names the OAuth subject as the caller, names three credential modes on the wire, keeps its service secrets in a registry separate from the API's, and builds its protected-resource document and 401 challenge from the mcp SDK. A second JWKS client, reusing PATHFINDER_SERVICE_TOKENS, accepting VEUPATHDB_AUTH_TOKEN from a caller, and hand-rolling the RFC 9728 document were all rejected.
tags: [security, auth, veupathdb, oauth, mcp, transport]
generated: { by: claude-code/opus-5, at: 2026-08-24T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-24T00:00:00Z }
status: stable
---

# What was decided

`veupathdb_mcp/auth.py` verifies one inbound `Authorization: Bearer` and
answers with an `McpCredential` naming one of three modes, the vocabulary the
admission record uses:

| Mode | What arrives | What the call may reach |
|---|---|---|
| `none` | nothing | nothing: the transport answers 401 with the challenge |
| `service` | a secret from `WDK_MCP_SERVICE_TOKENS`, naming an application | user-independent reads only |
| `veupathdb_user` | the user's registered VEuPathDB bearer | that user's own WDK resources |

`wdk_identity()` publishes the request token on `veupathdb_auth_token_ctx` in
user mode only. In service mode the context stays empty, so the transport guard
that refuses a `/users/<id>/...` call without a request token still holds and
the service account keeps its confinement
([a WDK-backed feature requires a registered VEuPathDB login](wdk-requires-registered-login.md)).

The VEuPathDB half of the verification is
`veupathdb/wdk/auth_login.py::validate_oauth_token`, the client
library's own ES512 check, wrapped by `veupathdb_mcp/identity.py::resolve_oauth_subject`,
which caches the subject a token names for five minutes. The application's API
calls the same verifier and then maps the user onto its `users` table
([a VEuPathDB bearer token is the user](bearer-identity-and-service-tokens.md));
the MCP server stops at the subject, so it reads no PathFinder table
([the MCP server writes no PathFinder table](the-mcp-server-writes-no-pathfinder-table.md)).
`McpCredential.client_id` is that subject string.

`veupathdb_mcp/metadata.py` builds the RFC 9728 document route and the 401
`WWW-Authenticate` challenge from the `mcp` SDK's own
`create_protected_resource_routes` and `RequireAuthMiddleware`.

# What was rejected

**A second JWKS client inside the MCP process.** It would hold its own signing
key and its own 120-second window, so one process could accept a token the
other refuses, and a key rotation would be visible twice at different times.
Reuse also carries the 503 rule for free: a JWKS that cannot be read names the
identity provider rather than blaming the credential.

**Naming the caller by PathFinder's internal user id.** It reads the `users`
table on every admission, which a second deployment of the server cannot do,
and the id was only ever stringified into `client_id`.

**Reusing `PATHFINDER_SERVICE_TOKENS` for the MCP server's service mode.** A
secret a caller sends to an MCP server would then also authenticate to the
application's own API as that application. The MCP server therefore reads a
separate `WDK_MCP_SERVICE_TOKENS`, parsed by the same registry type.

**Accepting `VEUPATHDB_AUTH_TOKEN` from a caller.** The service account is
confined by a transport guard rather than by call sites; a caller that could
present it would carry that confinement past the guard. It stays the server's
own outbound credential and is never an inbound one.

**Hand-rolling the protected-resource document and the challenge header.** The
`mcp` distribution that pins the protocol revision already models RFC 9728 and
already builds the `resource_metadata=` challenge. A second copy would drift
from the revision the rest of the stack is pinned to.

**Validating `aud`.** A site mints its tokens for its own client id, so a token
the server receives carries the website's audience, not the server's. Enforcing
it would refuse every real token. The MCP specification requires audience
binding, so this is a named deviation that closes only when the authorization
server can mint audience-bound tokens.

# One installation fact

`pydantic-ai` brings `fastmcp-slim` in its client extra only, so the auth
surface builds on `mcp`, which is complete and arrives with `pydantic-ai`. The
api names `fastmcp-slim[server]` in its own dependencies for the served server
([the wdk-mcp server is a product module](the-wdk-mcp-server-is-a-product-module.md)).
`VEuPathDBTokenVerifier` satisfies the SDK's `TokenVerifier` protocol, which
every FastMCP auth provider extends, so either path consumes it unchanged.
