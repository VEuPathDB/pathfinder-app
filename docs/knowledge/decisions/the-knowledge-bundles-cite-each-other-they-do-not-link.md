---
type: Decision
title: The two knowledge bundles cite each other, they do not link
description: A markdown link that crosses the boundary between this bundle and veupathdb-py's is replaced by a backticked citation of the sibling repository path, because the two repositories are never checked out side by side. 45 relative links died in a standalone copy of veupathdb-py; 30 became citations, 15 left with the two PathFinder proposals that moved back here, and 98 links in the reverse direction became citations too. GitHub URLs into the other repository were rejected.
tags: [veupathdb-py, split, knowledge-bundle, okf, docs, check-knowledge]
generated: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
status: stable
---

# What was decided

A markdown link whose target leaves the bundle that holds it is not a link. It is
a citation, written as backticked prose that names the sibling repository and the
path inside it:

```
the registered-login rule (`pathfinder: docs/knowledge/decisions/wdk-requires-registered-login.md`)
WDK-ANS-009 (`veupathdb-py: docs/knowledge/wdk/rules/searches-and-answers.md`)
```

Inside `veupathdb-py: docs/knowledge/` the prefix is `pathfinder:`. Inside this
repository's `docs/knowledge/` it is `veupathdb-py:`. A relative path across the
boundary never appears in either direction.

Two documents were not citations to write but files in the wrong bundle.
`eda/pathfinder-architecture-fit.md` and `eda/pathfinder-integration-concept.md`
are proposals about PathFinder's layers, tools and durable jobs, not facts about
EDA, so they moved to `docs/knowledge/eda/` here. The library's `eda/index.md`
lost its `## PathFinder` section; this bundle's root index gained an EDA section.

The `- anchor:`, `- status:`, `- upstream:` and `- reason:` fields of a `rules/*.md`
block carry filesystem paths that `scripts/check-wdk-rules.mjs` resolves, not links
a reader follows. A field naming a path in another repository carries the same
citation prefix, and the checker reads it as a citation instead of resolving it;
the run reports how many rules are anchored that way.

A prefix names a repository: `veupathdb-py` is `VEuPathDB/ai-veupathdb-client`,
`veupathdb-mcp` is `VEuPathDB/ai-wdk-mcp`, `assistant-platform` is
`VEuPathDB/ai-assistant-platform`, and `pathfinder` is `VEuPathDB/pathfinder-app`.

# The measurement

The client is published as its own GitHub repository. Copied out of this
checkout, its own `node scripts/check-knowledge.mjs` exited 1 with **45**
`link does not resolve` errors, every one of them a relative path into this
monorepo's `docs/knowledge/`. In place the same command reported 0 violations,
because this checkout still holds the targets.

| direction | links | outcome |
| --- | --- | --- |
| library -> monorepo | 45 | 15 left with the two returning proposals, 30 became citations |
| monorepo -> library | 98 | 96 became citations, 2 are the returning proposals and became local links |

Two further links live in `conventions/verification-gates.md`, which another
change owns.

# What would falsify this

`node scripts/check-knowledge.mjs` at the repository root, and the same command
run inside a copy of the client made outside this checkout. Both must exit 0.
The second is the one that matters: it is the only invocation that sees what a
reader of the published repository sees.

# What was rejected

**A GitHub URL into the other repository**, of the form
`https://github.com/<org>/veupathdb-py: blob/main/docs/knowledge/wdk/rules/auth-and-transport.md`.
An unpinned branch URL rots exactly as silently as a dead relative path: the file
is renamed and the link 404s with nothing in either repository failing. A URL
pinned to a sha is stale on the first edit of the target and cites text that no
longer says what the citing sentence claims. `check-knowledge.mjs` skips any target
carrying a scheme, so neither form is checked by anything.

**Keep the relative links and accept the failing gate in the published repository.**
The gate is the library's own CI `package` job. A repository that ships red is a
repository whose next real failure is not read.
