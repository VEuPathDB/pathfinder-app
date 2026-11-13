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
- The mark is unchanged. The lockup sets a small `VEuPathDB` above `Strategist`.
- A source scan on each side refuses the old name in any string a researcher can read:
  `apps/web/src/vocabulary.test.ts` and `tests/unit/test_the_product_is_named_strategist.py`.

## What keeps the old name, and why

Names that only this repository writes and reads are `strategist`: the shared TypeScript
package (`@strategist/shared`), the components, the brand files, the browser storage keys
(moved once on load, so no setting resets), the `STRATEGIST_*` settings no deployment sets,
the `X-Strategist-Service-Token` header, the dev-login cookie, and `bin/strategist-worker`, the
command the worker starts from.

Each of these is read by something outside one release, so it keeps `pathfinder` until it
moves with its reader:

- The Python package `pathfinder`. A saved conversation stores the module path of every
  type in its checkpoint, and the serializer's allowlist reads it.
- `assistant_id` (`"pathfinder"`) in stored rows, and `application_id`, which is also the key
  of the MCP service-token secrets puppet writes.
- `PATHFINDER_WDK_MCP_URL` and `PATHFINDER_RESEARCH_MCP_URL`, which the quadlet env files set.
- `__pathfinder_internal__:`, the prefix that hides and cleans helper strategies in WDK
  accounts. A new prefix would show helpers stranded under the old one; it stays.
- The type of the location message the frame sends, which the site's page listens for.
- The `PathFinder/` User-Agent, which VEuPathDB operations reads.
- The `/pathfinder` path, which the site route and the site proxy name.
- Metric and trace service names, image, database and repository names.

The [rename backlog item](../backlog/the-identifiers-take-the-strategist-name.md) moves each
one with what reads it.

## Rejected

- **One mass replacement of every spelling.** It renames the package under saved
  conversations and the worker command under the estate, so existing threads fail to load and
  the worker does not start until the estate changes on the same day.
- **A configurable base path now.** Next.js fixes the base path when the image is built, so
  one image cannot serve two paths; the path moves with the site route and the proxy.
