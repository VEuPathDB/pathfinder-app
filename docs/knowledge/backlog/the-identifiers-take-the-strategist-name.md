---
type: Backlog
title: The identifiers take the Strategist name
description: Everything but the repository name says Strategist. The repository moves on GitHub.
tags: [rename, release, deploy, frontend]
generated: { by: claude-code/opus-5.5, at: 2026-11-14T00:00:00Z }
status: proposed
---

# The identifiers take the Strategist name

The [naming decision](../decisions/the-product-is-named-veupathdb-strategist.md) lists what
already moved. What is left:

- **The repository** `VEuPathDB/pathfinder-app`: rename it on GitHub, then move what names it
  in one change: the User-Agent (`platform/identity.py`), the Sphinx links, the issue links in
  this bundle, the documentation host `veupathdb-pathfinder.readthedocs.io`, and the
  knowledge citation prefix `pathfinder:` with the three library bundles that write it.
