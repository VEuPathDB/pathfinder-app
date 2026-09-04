---
type: Decision
title: The EDA permissions cache is keyed by the credential the call carries, not by the WDK user id it resolves to
description: services/eda/catalog.py addresses the /eda/permissions answer by the site and a sha256 of the request's VEuPathDB token. Keying by the numeric WDK user id from /users/current was rejected, because identity resolution costs a WDK round trip that buys only cross-token dedup for one account, and it puts a WDK dependency in a pure-EDA read path.
tags: [eda, security, caching, services]
generated: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-30T00:00:00Z }
status: stable
---

# What was decided

`_permissions(site_id)` addresses its cache entry as
`f"{site_id}|{sha256(token)}"`, where the token is the request's
`veupathdb_auth_token_ctx`. A call that carries no token raises
`WDKLoginRequiredError` before it reaches the address, which is the error the
EDA client raises for the same request anyway. The map is capped at 512
entries and dropped whole when the cap is reached, beside the other
module-level catalog maps.

`studies` stays keyed by the site alone. The `/eda/studies` listing is the
same for every account, and only `permissions` decides what an account may
read.

# What was rejected

**Keying by the numeric WDK user id.** `/users/current` under the request's
token names the account, so two tokens of one user would share one entry. It
was rejected on three counts. It adds a WDK round trip to a read that is
otherwise pure EDA, so a WDK outage makes the study catalog unusable. To avoid
paying that trip on every call the token-to-id mapping has to be cached, and
that cache is keyed by the token, so the round trip buys only the dedup of two
tokens belonging to one account. And it makes `resolve_dataset` depend on a
second service, which every EDA test would then have to double: the suites
that drive the catalog install an EDA transport and nothing else.

**Dropping the cache and reading `/permissions` per call.** The map is read by
`resolve_dataset`, `search_studies` and `browse_studies`, so one authoring turn
asks several times. The read is a full catalog for the account and the answer
does not change inside a turn.

# The consequence, stated

Two credentials in one api or worker process hold two authorization maps. A
restricted account is never offered a dataset another account's token
unlocked, and `UnknownEdaDatasetError` names what that account cannot reach.
One account that signs in twice pays one extra `/permissions` read, which is
the price of not calling WDK on every catalog read.

# Anchor

`apps/api/src/pathfinder/services/eda/catalog.py`, pinned by
`apps/api/src/pathfinder/tests/unit/services/eda/test_dataset_resolution.py`:
a second token reads its own map, two accounts browse different catalogs, and
one account asking twice still reads once.
