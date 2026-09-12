---
type: Backlog
---

# The thread adds up the roots of a split graph

**What I did.** Built a plasmodb graph with two roots, which is what an edit that detaches a
fragment leaves behind: `step_a1b2c3d4` (`GenesByGoTerm`, WDK step 440432473, 1282 genes) and
`step_b5c6d7e8` (`GenesByText`, WDK step 440432474, 61 genes), neither consuming the other.
Then produced the graph snapshot the turn emits and the summary `get_strategy` returns for the
same session.

**What I got.** `data-graph-snapshot` ->
`{"strategyId": "g1", "geneCount": 1343, "nodes": [{"id": "step_a1b2c3d4", "searchName": "GenesByGoTerm", "estimatedSize": 1282}, {"id": "step_b5c6d7e8", "searchName": "GenesByText", "estimatedSize": 61}], "edges": []}`,
so the thread draws "2 steps, 1,343 genes". In the same turn `get_strategy` answers
`"2 steps, count not available"` with status `warn`.

**Why that's wrong.** 1343 is the size of no result: 1282 and 61 are two unrelated sets, and
nothing ran a query that returned 1343 genes. A reader who cites the figure cites a number the
site never answered, and the two surfaces of one turn contradict each other, so whichever the
reader believes, one of them lied.

**Why it happens.** `_root_total` (`apps/api/src/pathfinder/ai/tools/standalone/_stream_parts.py`)
sums `_count_for_step` over every member of `graph.roots`. `_root_count`
(`apps/api/src/pathfinder/ai/tools/standalone/strategy_graph.py`) and `read_live_state`
(`apps/api/src/pathfinder/ai/lead/live_state.py`) already apply the other rule: a count only
when the graph has exactly one root.

**Fix.** The snapshot reports the citable count of the primary root
(`StrategyGraph.primary_root_id`), and nothing when the graph has no single root, so all three
surfaces answer the same question. A detached fragment keeps its own per-node count.

**What you'd get.** The same graph sends `"geneCount": null` and the thread draws
"2 steps, count not available", the sentence `get_strategy` already returns. A one-root graph
is unchanged.
