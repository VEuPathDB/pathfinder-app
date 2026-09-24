---
type: Reference
title: Which repository wins, and which sites this application is verified on
description: The authority ranking PathFinder reads the upstream repositories under, the two sites its own work is confirmed on, and the one test shape that looks like evidence and is not.
tags: [wdk-alignment, sources, verification, pathfinder]
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
status: stable
---

# The ranking

The pinned repositories, their shas and what each one is authoritative for are
`veupathdb-py: docs/knowledge/wdk/sources.md`. What that page states neutrally, this
application states as a rule about itself.

[VEuPathDB/WDK](https://github.com/VEuPathDB/WDK/tree/e534d2e6a5119165e1742c7a9e07a371217ddda5/):

> Highest authority: when PathFinder and this repository disagree, PathFinder is wrong.

[VEuPathDB/web-monorepo](https://github.com/VEuPathDB/web-monorepo/tree/63d1705463d553c0ac19ee577c1b09666597b903/):

> `packages/libs/wdk-client` carries the TypeScript types PathFinder's own types must match

The mapping those types are held to is [what corresponds to
what](type-correspondence.md).

# The two sites

plasmodb.org:

> Primary site for PathFinder's own work.

toxodb.org is the second. orthomcl.org is used by the client bundle once, as a contrast,
and it runs a site model neither of these two runs:

> a claim that holds on plasmodb.org and toxodb.org and orthomcl.org is not thereby a
> claim about the two sites PathFinder actually uses.

# A test that would break is not a test that checks

A live end-to-end run of an analysis would fail if the form defaults stopped being sent.
It is still not evidence for that rule: it asserts nothing about parameters, it is gated
on `live_wdk` credentials so it does not run in CI, and it fails for many unrelated
reasons. PathFinder runs no analysis of its own since the site took GO, pathway and word
enrichment back ([VERIFY shows its evidence](../../decisions/verify-shows-its-evidence.md)).

The defaults themselves are the tool server's: `veupathdb-mcp:
src/veupathdb_mcp/wdk/params.py` reads the form document and copies every
`initialDisplayValue` into the create payload, and the rule that the defaults are inert
until a client sends them back is WDK-VALID-011 (`veupathdb-py:
docs/knowledge/wdk/rules/validation.md`).
