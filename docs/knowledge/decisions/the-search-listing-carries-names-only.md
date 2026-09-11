---
type: Decision
title: The search listing carries names only
description: list_searches returns the search names of a record type and nothing else, so the portal's 2769-search listing costs 50248 estimated tokens instead of 143656 and stays under the runtime's compaction threshold. A page size over the ontology order, and a category axis on the served listing, were rejected.
tags: [frame, catalog, compaction, portal]
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
status: stable
---

# What was decided

**`list_searches` returns a list of names.** `ai/tools/standalone/catalog.py`
projects the served `SearchListing` rows onto `listing.name` and returns that
list. The display name, the description, the category and the ranking come
from `search_for_searches`, and the ontology index comes from
`browse_search_categories`.

**The size is pinned by a test.** `tests/unit/ai/tools/test_catalog_listing_size.py`
builds a listing at the portal's measured count and text length, runs it
through the tool, and asserts `compact_history` leaves a FRAME history that
carries it untouched, so the pin fails if a second column returns. A third
test compacts the same history built from name-and-display-name rows, which
shows the first assertion is not true of any 2769-row payload.

# Why

The listing's only structural job is to widen the enum that guards
`set_criterion`, `get_search_overview` and `get_parameter_options`: every name
it shows enters `agent_state.catalog_search_names`. A name is what the guard
reads and what the next call sends, so the second column bought nothing the
ranked search does not already give with more context.

The portal is the size case. Its transcript listing holds 2769 searches:
574624 characters as `{name, displayName}` rows, about 143656 estimated tokens
at four characters per token, against `COMPACT_AT_ESTIMATED_TOKENS` of 100000.
Every FRAME request on the portal therefore carried more than the threshold and
the in-run compaction rewrote the history on each step. Names only is 200992
characters, about 50248 estimated tokens. PlasmoDB's listing falls from 15174
to 5549.

# What was rejected

**A page size.** The listing arrives in the site's own ontology order, which
interleaves the categories: on the portal the general searches sit at indices
0, 11, 28 and on to 2768, so a first page of any size drops searches FRAME
binds while keeping dataset searches it never picks by browsing. Paging the
whole listing costs what the whole listing costs.

**A category axis on the listing.** Filtering to one ontology category bounds
the portal at its largest category, 848 searches and about 17500 estimated
tokens as names, and it matches how a site's search menu is organized. It reads
a WDK search per row, so it belongs to `veupathdb-mcp`, whose served
`list_searches` and `tool_payloads.list_search_listings` take a site and a
record type and nothing else. Names only holds the threshold without that
release, and the axis stays available if a site's listing outgrows it.

**The scripted FRAME reads the digest by its line shape.**
`ai/models/mock/history.py` recognizes a compaction digest by the
`- <tool>(<args>) -> <result>` lines the runtime writes, a shape no runtime
surface publishes. `test_mock_compacted_history.py` builds its digest through
the real `compact_history`, so a runtime release that reformats the digest
turns that unit test red rather than an e2e run.

**The Lead's history is not the size case.** The Lead's script still routes on
the last user text, which a compaction would replace with the digest. Across
one full e2e run before this change (165 journeys) every one of the 2584
compaction log lines carried the FRAME signature, 7 input messages at about
148000 estimated tokens, and none came from a Lead history. The count of
compaction lines in an e2e run after this change is the measurement that says
whether that holds.
