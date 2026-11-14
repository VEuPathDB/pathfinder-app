---
type: Decision
title: The product is named VEuPathDB Strategist, and the screen changes before the identifiers
description: Every string a researcher reads names the product VEuPathDB Strategist where the name stands alone and Strategist in running text. Identifiers, stored values and names other systems send or match keep `pathfinder` until a release that moves each one with what reads it.
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

Each of these is read by something outside one release, so it keeps `pathfinder` until it
moves with its reader:

- `application_id` (`"pathfinder"`), which is also the key of the MCP service-token secrets
  puppet writes.
- The type of the location message the frame sends, which the site's page listens for.
- The `/pathfinder` path, which the site route and the site proxy name.
- Image, quadlet unit, volume, database and repository names.

The [rename backlog item](../backlog/the-identifiers-take-the-strategist-name.md) moves each
one with what reads it.

## Rejected

- **A module alias that keeps `pathfinder` importable for saved threads.** It is a second
  name for every module, kept for as long as one old checkpoint exists. A migration rewrites
  the stored names once.
- **One mass replacement of every spelling.** It renames the package under saved
  conversations and the worker command under the estate, so existing threads fail to load and
  the worker does not start until the estate changes on the same day.
- **A configurable base path now.** Next.js fixes the base path when the image is built, so
  one image cannot serve two paths; the path moves with the site route and the proxy.
