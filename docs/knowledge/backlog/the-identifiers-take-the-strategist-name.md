---
type: Backlog
title: The identifiers take the Strategist name
description: Strategist answers to both names while the website and the estate move; then the transition names go, the repository moves on GitHub, and the links switch to /app/strategist.
tags: [rename, release, deploy, frontend]
generated: { by: claude-code/opus-5.5, at: 2026-11-14T00:00:00Z }
status: proposed
---

# The identifiers take the Strategist name

The [naming decision](../decisions/the-product-is-named-veupathdb-strategist.md) lists what
already moved. What is left:

- **The transition names**, once the estate runs the `strategist` stack, the websites proxy
  `/strategist` and read `strategistUrl`, and no stage lists `pathfinder-*` in tagger: build
  under `/strategist` (`BASE_PATH` on both sides) and drop the `/strategist` rewrite, post only
  `strategist:location`, build the web image against `http://strategist-api:8000`, publish
  and promote only `strategist-*` (`Jenkinsfile`, `scripts/release.mjs`), and drop the
  `pathfinder` fallback in `platform/tool_sources.py::_own_secret` and
  `FORMER_APPLICATION_ID`. The estate drops its `pathfinder-api` alias and former host, and
  the website redirects `/pathfinder/*` to `/strategist/*`.
- **The repository** `VEuPathDB/pathfinder-app`: rename it on GitHub, then move what names it
  in one change: the User-Agent (`platform/identity.py`), the Sphinx links, the issue links in
  this bundle, the documentation host `veupathdb-pathfinder.readthedocs.io`, and the
  knowledge citation prefix `pathfinder:` with the three library bundles that write it.
- **The site page address** `/app/pathfinder` to `/app/strategist`: VEuPathDB/web-monorepo#1946
  moves the route and redirects the old one. Once the sites run it, this repository's links to
  the site page (`services/site_pages.py`, share links) and the tests that spell it name
  `/app/strategist`.
