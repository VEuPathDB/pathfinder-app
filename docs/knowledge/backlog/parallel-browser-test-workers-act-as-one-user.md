---
type: Backlog
title: Parallel browser test workers act as one user
description: Every Playwright worker carries the registered account's website login, and a website login names that account's PathFinder user ahead of the dev-login cookie, so the two workers of a shard share one user's conversations, gene sets and memories; give each worker a user of its own or run one worker per stack.
tags: [frontend, e2e, identity]
generated: { by: claude-code/opus-5.5, at: 2026-10-31T00:00:00Z }
status: proposed
---

# Parallel browser test workers act as one user

## What happens

`e2e/fixtures/test.ts` signs each worker in with `POST /api/v1/dev/login?user_id=worker-{N}`
and puts the registered account's token in the `Authorization` cookie. Since the site login
became the only browser credential
([pathfinder-signs-in-through-the-site-that-hosts-it](../decisions/pathfinder-signs-in-through-the-site-that-hosts-it.md)),
`platform/security.py::_identify` reads the website login before the dev-login cookie, so
every worker is the account's own PathFinder user. `playwright.config.ts` runs two workers
per shard, and a spec that purges a site's data (A4) or reads "no conversations yet" runs
against the other worker's rows.

The suite passed with `--workers=1` on 2026-10-31; it was not run with two workers.

## Done when

Two workers of one stack never read or delete each other's rows: either each worker acts
as a user of its own while WDK calls still carry the registered token, or the config runs
one worker per stack and CI shards carry the parallelism.
