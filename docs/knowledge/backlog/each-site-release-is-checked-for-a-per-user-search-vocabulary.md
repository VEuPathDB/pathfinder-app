---
type: Backlog
title: Each site release is checked for a per-user search vocabulary
description: The catalog shares one copy of each search definition across logins, which holds only while no gene search lists a user's own data; every VEuPathDB release is checked for a search vocabulary that takes user_id.
tags: [wdk, catalog, users, release-check]
generated: { by: claude-code/opus-5.5, at: 2026-10-19T00:00:00Z }
status: proposed
---

# Each site release is checked for a per-user search vocabulary

WDK builds a search definition for the user who asks, and a vocabulary query may take
that user's id (veupathdb-py WDK-VOCAB-008). The WDK catalog in veupathdb-mcp keeps one
copy of each definition per site and serves it to every login
(`ai-wdk-mcp: docs/knowledge/decisions/the-catalog-shares-a-search-definition-across-logins.md`).
That is correct only while no gene search has such a vocabulary. On 2026-10-19 the one
vocabulary that takes `user_id`, `datasetVQ.geneListUserDataset` in EbrcModelCommon, feeds
the `datasetSelection` parameter of a step analysis form and no search.

A canvas save, a turn and a job read definitions through the site client inside
`search_definitions_read_once`, keyed by login, so they are not affected.

**At each VEuPathDB release:**

- Search ApiCommonModel and EbrcModelCommon at the release tag for a vocabulary query that
  names `InternalParams.user_id`, and for every parameter that reads it:
  `gh api -X GET search/code -f q='"InternalParams.user_id" repo:VEuPathDB/<repo>'`.
- For each parameter found, check whether a search in a question set uses it.
- If one does: the catalog's copy shows the first login's choices to every other login.
  Key that search's definition by login in `SearchCatalog.get_search_details`, with a test
  that two logins read their own choices, and release veupathdb-mcp.

This card stays while the catalog shares definitions across logins. It leaves the backlog
when the catalog keys every definition by login or WDK marks the per-user vocabularies in
the definition it sends.
