---
type: Decision
title: The product is named VEuPathDB Strategist, and the screen changes before the identifiers
description: Every string a researcher reads names the product VEuPathDB Strategist where the name stands alone and Strategist in running text. Every identifier moved to `strategist` with what reads it; the repository name and the site page address are the two that remain, and stored former names are read, never written.
tags: [decision, copy, brand, frontend, release]
generated: { by: claude-code/opus-5.5, at: 2026-11-13T00:00:00Z }
status: stable
---

## The rule

- **Where the name stands alone** (a browser title, the logo label, the lockup, the
  OpenAPI title, the export header, the README heading) it is **VEuPathDB Strategist**.
- **In running text** (a notice, a setting, a help sentence, a refusal, a prompt) it is
  **Strategist**.
- The mark is unchanged. The lockup sets `VEuPathDB Strategist` on one line beside it, and
  so does the sign-in card.
- A source scan on each side refuses the old name in any string a researcher can read:
  `apps/web/src/vocabulary.test.ts` and `tests/unit/test_the_product_is_named_strategist.py`.

## What keeps the old name, and why

Names that only this repository writes and reads are `strategist`: the shared TypeScript
package (`@strategist/shared`), the components, the brand files, the browser storage keys
(moved once on load, so no setting resets), the `STRATEGIST_*` settings no deployment sets,
the `X-Strategist-Service-Token` header, the dev-login cookie, and `bin/strategist-worker`, the
command the worker starts from.

A helper strategy is written as `__strategist_internal__:control test` (or `step counts`,
`control separation`): the prefix says whose it is, so the name carries no product word.
Helpers written under the old name stay hidden and cleaned: the deployment lists
`__pathfinder_internal__:Pathfinder `, `__pathfinder_internal__:Strategist ` and
`__pathfinder_internal__:` as former prefixes (veupathdb-py 0.9.0b5), longest first, so
stripping one leaves the same `control test ...` a new helper carries.

The Python package is `strategist` (distribution `strategist-api`), and the assistant id is
`"strategist"`. They moved after the estate started the worker by `bin/strategist-worker`,
because a worker started as `-m pathfinder.jobs.worker` does not start from this image.

- **Saved conversations.** A checkpoint names the module of every type it holds: the msgpack
  serializer writes each type as an extension whose payload starts with the module and the
  class name. Migration `2026_11_13_0001` decodes each `msgpack` row of `checkpoint_blobs` and
  `checkpoint_writes` that holds the old name, renames a module `pathfinder` or
  `pathfinder.*` to `strategist`, and encodes it again; every other byte stays as it was. It
  reads 200 rows at a time. `checkpoints` holds no module: its `checkpoint` column keeps only
  inline primitives and its `metadata` only the run's metadata. The downgrade renames back.
- **Stored assistant ids.** Migration `2026_11_13_0002` renames `"pathfinder"` to
  `"strategist"` in `conversations.assistant_id`, `eval_staged_cases` (its column and its
  extract) and the queued `chat_turn` jobs (the payload and its body).
- **The User-Agent, metrics and traces.** Every request to a site sends `Strategist/<version>`,
  the Prometheus series are `strategist_*` and the trace services `strategist-api` and
  `strategist-worker`. The worker reads its tool servers from `STRATEGIST_WDK_MCP_URL` and
  `STRATEGIST_RESEARCH_MCP_URL`. A chat body that names `"pathfinder"` names an assistant no deployment
  serves.
- **The application id and the estate stack.** The application id is `"strategist"`. Migration
  `2026_11_14_0001` renames `pathfinder` to `strategist` in every `application_id` column and
  every column default, moves each memory from the store prefix `app.pathfinder.` to
  `app.strategist.`, and reseals each stored provider key, whose associated data names the
  application. The estate's `strategist` stack names its units, volumes, secrets, database
  and role `strategist`.
- **Both names, until every owner has moved.** The website, the estate stack and this
  repository each move on their own day, so for one transition this repository answers to
  both names. Jenkins publishes `veupathdb/pathfinder-*` and `veupathdb/strategist-*` from one
  build and the release promotes all four. Strategist is built under `/pathfinder` and Next
  rewrites every `/strategist` address onto it, so a website that proxies either path frames
  it. The frame posts its location as `strategist:location` and as the former type. The web image reaches
  the api at `pathfinder-api`, an alias the `strategist` stack keeps. The worker presents the
  service-token secret listed under `strategist`, or under `pathfinder` when only that entry
  exists. The [rename backlog item](../backlog/the-identifiers-take-the-strategist-name.md)
  lists what goes once every owner has moved.
- **Local names.** The local and test databases are `strategist` and `strategist_test` (the
  integration guard refuses any other), the e2e images `strategist-e2e-api` and
  `strategist-e2e-web`, the root workspace `strategist`, and the local Langfuse defaults name
  Strategist. The nightly MCP lane reads the secret `STRATEGIST_MCP_SERVICE_TOKENS`.

What still says `pathfinder`, and why:

- **Former names that are read, never written.** The former helper prefixes above, the
  migrations that move stored values (they name the old value), the browser storage keys moved
  on load, and the absent `pathfinder-auth` cookie the tests assert no module names.
- **Names the sites store.** The UAT uploads (`pathfinder-uat-*`) and the live-check datasets
  on the test account keep the names they were uploaded under.
- **The repository** `VEuPathDB/pathfinder-app`, which the User-Agent, Jenkins, the
  documentation host and the knowledge citation prefix name.
- **The site page address** `/app/pathfinder`, which the websites serve until they deploy
  `/app/strategist`.
- **The transition names** under "Both names" above.

The [rename backlog item](../backlog/the-identifiers-take-the-strategist-name.md) moves the
last three.

## Rejected

- **A module alias that keeps `pathfinder` importable for saved threads.** It is a second
  name for every module, kept for as long as one old checkpoint exists. A migration rewrites
  the stored names once.
- **One mass replacement of every spelling.** It renames the package under saved
  conversations and the worker command under the estate, so existing threads fail to load and
  the worker does not start until the estate changes on the same day.
- **One day on which every owner moves together.** The website build, the estate cutover
  and this release belong to three teams; answering to both names lets each merge when it is
  ready.
- **Building under `/strategist` and rewriting `/pathfinder` onto it.** A page served through
  the former proxy would then ask for its scripts under `/strategist`, which that website
  does not yet proxy.
