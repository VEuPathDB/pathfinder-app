---
type: Decision
title: E2E replays recorded WDK
description: The Playwright suite reaches VEuPathDB only through the wdk-wire proxy, which replays committed QA recordings and answers 418 for any request it holds none for; each test signs its own token and is its own Strategist user; recording and the refresh run by hand on cedar. The one exception to "only mock the LLM", for e2e only. A transport inside the clients, a plain HTTP replay server, browser routing and a live tier were rejected.
tags: [testing, e2e, ci, recording, replay]
generated: { by: claude-code/opus-5.5, at: 2026-11-24T00:00:00Z }
status: stable
---

# What was decided

**The e2e tier replays WDK; the other tiers keep their rules.** Unit and integration tests
still mock only the LLM. The Playwright suite runs with `docker-compose.e2e-wire.yml`
layered on the e2e overlay: `api` and `worker` reach every VEuPathDB host through
`HTTPS_PROXY=http://wdk-wire:8080` and trust the proxy's CA through `SSL_CERT_FILE`, with no
change to production code, and every QA host and `api.openai.com` maps to `127.0.0.1` in
their `extra_hosts`, so a client that ignored the proxy would fail on a refused
connection. `wdk-wire` runs `veupathdb.testing.wire` (veupathdb-py's `wire` extra, at the
tag the overlay names; the library's own decision is `a-wire-replays-what-wdk-answered.md`).

| piece | where |
|---|---|
| recordings, at most 40 MB, catalogs gzipped | `apps/web/e2e/wire/` (`manifest.json`, `stack.jsonl`, `cassettes/`, `bodies/`, `catalogs/`) |
| the proxy image | `deploy/wdk-wire/Dockerfile` |
| replay and record overlays | `docker-compose.e2e-wire.yml`, `docker-compose.e2e-wire-record.yml` |
| the test's token, `begin` and `end` | `apps/web/e2e/fixtures/wire.ts`, `wire-recordings.ts` |
| redaction and size gate | `scripts/check-wire-recordings.mjs` (pre-commit and CI) |
| the commands | `scripts/e2e-wire.sh replay`, `catalogs`, `record --test <spec:line>` or `--all`, `refresh` |

**A test names its recordings by its token.** The cassette id is the project, the spec file
and the title path, slugged, with an eight-character hash. In replay the `_wire` fixture
signs an ES512 token with the P-521 key `wdk-wire` made when it started (read once by global
setup from `/__wire/signing-key` on the loopback port 8181), carrying the cassette id in
`e2e_cassette`. The stack's `VEUPATHDB_OAUTH_URL` is `https://auth.wire.test`, a name only the
proxy answers, so `validate_oauth_token` verifies the token unchanged. The proxy answers
`/users/current` with `e2e+<hash>@strategist.test`, so every test is its own Strategist user
and starts empty at any worker count, and the data notice is continued per test. A
request with no registered token reads the shared `stack` recordings.

**A request with no recording fails its test.** The proxy answers 418 with `X-Wire-Miss: 1`,
and `end` returns the misses and every recorded write the app did not send; the fixture
fails the test with them and names the record command, even when the page absorbed the
error. A miss on `stack` fails the run in global teardown. A site whose snapshot did not
load fails global setup.

**Recording and the refresh are by hand, on cedar, against QA.** Nothing schedules them.
`catalogs` builds the 7 catalog snapshots through the e2e api image; a record run needs
them first, because a catalog the api builds through the recorder would be recorded.
`record` (`--test <spec:line>`, or `--all` for the first set) runs the named tests with one worker as the registered account, keeps only the
tests that passed, replays them as a self-check, then merges them into the tree. `refresh`
re-sends every recording to QA with the minted ids mapped, rebuilds the 7 catalog snapshots
through the e2e api image, runs the gate and the replay suite, and writes
`refresh-report.md` for the commit or PR. Both writers redact the account, its token and
every cookie, and refuse to write a recording in which any of them is still found.

**Workers.** A local run takes 4 Playwright workers, a CI shard 2 (4 shards), a record run 1.
The account lock and the `@whole-account` tag are gone: no two tests share a user in
replay, and a record run is serial.

# Rejected

- **A transport inside veupathdb-py, switched by an environment variable.** Nine client
  constructions on a production path, and replay state shared between the api and worker
  processes. The proxy holds it in one process.
- **Rewriting the site URLs to a plain HTTP replay server.** Record links, strategy URLs and
  the EDA and VDI origins derive from the site's host, so the URLs the specs assert on
  would change.
- **Playwright `page.route`.** It sees only the browser; every WDK call is server side.
- **A live tier.** It ties the suite to cedar and to QA's load and data on the day; the
  refresh is the live check, and it reports per test what WDK now answers differently.
