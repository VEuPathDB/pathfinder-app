---
type: Backlog
title: The identifiers take the Strategist name
description: Everything but the repository name and the UAT uploads says Strategist. The repository moves on GitHub, and the UAT uploads are made again under strategist names.
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
- **The UAT uploads** `pathfinder-uat-*` and the live-check datasets on the QA test account:
  upload them again under `strategist` names, record the fixtures and evals that spell them
  again, and delete the old uploads.
