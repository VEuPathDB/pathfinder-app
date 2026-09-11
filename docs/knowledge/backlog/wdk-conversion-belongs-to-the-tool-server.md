---
type: Backlog
title: The WDK to AST conversion names nothing of PathFinder's and belongs to the tool server
description: services/strategies/wdk_conversion.py is 263 lines that import zero pathfinder names, converting a library-owned WDK strategy into a library-owned AST with catalog parameter specs, so it sits in the app while both ends and its only dependency live in veupathdb_mcp.
tags: [strategies, wdk, veupathdb-mcp, layering, wrong-repo]
generated: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-11T00:00:00Z }
status: stable
---

# What I did

Read every import and every definition in
`apps/api/src/pathfinder/services/strategies/wdk_conversion.py`, then listed
its callers.

# What I got

263 lines. `grep -n pathfinder` over the file returns nothing. The imports
(lines 7-27) are `assistant_core.platform.logging`, ten modules under
`veupathdb.domain` and `veupathdb.wdk`, and
`veupathdb_mcp.catalog.adapt_param_specs_from_search` and
`get_search_params_under_context`. It defines two public functions,
`build_snapshot_from_wdk` (line 158) and `canonicalize_synced_parameters`
(line 212), over six private helpers.

Both ends of the conversion are library shapes: `WDKStrategyDetails` in, a
`StrategyAst` snapshot out, both from `veupathdb.domain.strategy`. The app
imports the two names in exactly two places,
`services/strategies/insert_saved.py:38` and
`services/strategies/wdk_sync.py:27`.

# Why that's wrong

The only distribution that may see both the WDK client and the catalog is
`veupathdb-mcp`, so today a second consumer that reads a saved WDK strategy has
to reimplement this conversion or copy it out of an application. A copy drifts:
this file encodes how a boolean operator is found, how an expanded reference
resolves and how a parameter is canonicalized, and a second copy that gets one
of those wrong builds a different strategy from the same WDK row.

# Why it happens

`wdk_conversion.py` was written beside the service that first needed it rather
than beside the shapes it converts.

# Fix

Library first, in `ai-wdk-mcp`: move the file into the `veupathdb_mcp.wdk`
package, beside `step_tree.py`, under a name that says what it converts; publish
`build_snapshot_from_wdk` and `canonicalize_synced_parameters` on that package
in `veupathdb-mcp: tests/unit/published_surface.json`, and move the two test
files with it. Then here: delete the module, point
`services/strategies/insert_saved.py` and `services/strategies/wdk_sync.py` at
the published names, and take it at the library's next tag.

# What you'd get

One conversion from a WDK strategy to an AST, owned by the distribution that
owns both shapes, reachable by any consumer of the tool server, and two import
lines in this repository instead of 263 lines of library code.
