# Backlog

Everything known to be outstanding, ranked by what actually moves the product. Each item stands alone: a fresh session should be able to pick one up without this conversation.

Items are removed when done, not marked done. The [log](../log.md) records
what left.

## Ranked

1. [replace_subtree can destroy the strategy](replace-subtree-can-destroy-the-strategy.md) - a recovery pass halved a correct 16-step tree and left `__input_step__` placeholders; the edit path's leaf-set invariant is missing here.
2. [The combination check under-enforces three or more terms](combination-lca-under-enforces-many-terms.md) - two-term constraints are exact; "A OR B OR C" accepts a tree that ANDs two branches.
3. [The portal search listing exceeds the compaction threshold](portal-search-listing-exceeds-the-compaction-threshold.md) - 2769 listings, about 144K tokens, so FRAME is compacted after every step on veupathdb.org and the scripted mock re-runs the build arc; two thread-surgery journeys are red on the portal.
4. [Re-cut the authoring model out of veupathdb-py](re-cut-the-authoring-model-out-of-veupathdb-py.md) - the client ships PathFinder's strategy authoring model because `veupathdb.wdk` names it: 47 measured edges into `ast`, `ops`, `tree`, `graph_model`, `session` and `operational_spec`.
5. [The SSE golden depends on when the title task finishes](sse-golden-depends-on-title-scheduling.md) - the title chunk's position in a turn is a scheduling outcome, so the simple-turn golden pins an order the runner does not guarantee.
6. [The test tree is type-checked by nothing](the-test-tree-is-type-checked-by-nothing.md) - mypy 1158 / pyright 1486 errors over `apps/api/src/pathfinder/tests`; a widened library type left a live assertion silently wrong until it ran.
7. [The tool server publishes no list of the tables it owns](the-tool-server-publishes-no-table-names.md) - the runtime publishes `OWNED_TABLES` and `VERSION_TABLE`; the tool server names its version table only inside its alembic environment, so the autogenerate filter holds one retyped literal.
8. [The tool server declares almost no public surface](the-tool-server-declares-almost-no-public-surface.md) - 66 names imported out of `veupathdb_mcp`, 52 of them submodules their own package never publishes, so a file rename in the tool server is an outage here.

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
