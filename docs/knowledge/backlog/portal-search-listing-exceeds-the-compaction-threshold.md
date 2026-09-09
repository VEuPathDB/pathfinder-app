---
type: Backlog
title: The portal search listing exceeds the in-run compaction threshold, so FRAME is compacted after every step
description: On veupathdb.org, list_searches returns 2769 listings (about 144K estimated tokens), above COMPACT_AT_ESTIMATED_TOKENS, so every FRAME request on the portal carries the whole catalog and in-run compaction fires on each step; the scripted mock cannot survive compaction, so no e2e journey builds on the portal.
tags: [frame, catalog, compaction, portal, mock]
generated: { by: claude-code/fable-5, at: 2026-09-03T00:00:00Z }
status: draft
---

# What is wrong

`services/tool_payloads.py::list_search_listings("veupathdb", "transcript")` returns 2769
`{name, displayName}` rows, 574,624 characters, about 144K estimated tokens at four characters
per token (plasmodb: 349 rows, about 15K tokens). `COMPACT_AT_ESTIMATED_TOKENS` in
`assistant-platform: packages/assistant-core/src/assistant_core/conversation/history/compaction.py`
is 100K, so on the portal `compact_history` rewrites
the FRAME history after every model step. Measured on the mock stack: one organism edit produced
72 `set_criterion` calls and hit the 40-request ceiling; the reply said "Substituted the organism"
and the AST leaf was unchanged.

# Why it happens

The `list_searches` return alone is larger than the compaction threshold, so compaction runs on
every request. The scripted mock (`ai/models/mock/__init__.py::_frame_script`) reads the work
order from the last user text and the bound reply from the visible history; after compaction both
are the digest, so it re-runs the build arc and re-binds the criterion.

# Fix

Two layers, both needed:

1. Product: the portal listing needs a bounded form (a page size, a category filter, or a
   names-only shape; names-only measured at about 50K tokens, under the threshold). Decide which
   shape the FRAME tools should read and pin it with a test that asserts the estimated token size
   of the portal listing stays under the threshold.
2. Mock: `_frame_script` reads the work order from the head request's first `UserPromptPart`
   and treats a compaction digest as history it has already acted on.

The thread-surgery journeys build on `plasmodb` (`e2e/feature/thread-surgery/prompts.ts::SITE_ID`),
whose listing fits, so no e2e spec covers a build on the portal until this lands.

# Done when

A one-criterion build on the portal logs zero `usage ceiling` lines, the AST leaf reads the
swapped organism after the edit, and a test pins the estimated token size of the portal listing
under the threshold.
