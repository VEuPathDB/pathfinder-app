# Backlog

Everything known to be outstanding, ranked by what actually moves the product. Each item stands alone: a fresh session should be able to pick one up without this conversation.

Items are removed when done, not marked done. The [log](../log.md) records
what left.

## Ranked

1. [replace_subtree can destroy the strategy](replace-subtree-can-destroy-the-strategy.md) - a recovery pass halved a correct 16-step tree and left `__input_step__` placeholders; the edit path's leaf-set invariant is missing here.
2. [The combination check under-enforces three or more terms](combination-lca-under-enforces-many-terms.md) - two-term constraints are exact; "A OR B OR C" accepts a tree that ANDs two branches.
3. [The portal search listing exceeds the compaction threshold](portal-search-listing-exceeds-the-compaction-threshold.md) - 2769 listings, about 144K tokens, so FRAME is compacted after every step on veupathdb.org and the scripted mock re-runs the build arc; two thread-surgery journeys are red on the portal.
4. [Re-cut the authoring model out of veupathdb-py](re-cut-the-authoring-model-out-of-veupathdb-py.md) - the client ships PathFinder's strategy authoring model because `veupathdb.wdk` names it: 47 measured edges into `ast`, `ops`, `tree`, `graph_model`, `session` and `operational_spec`.
5. [Adopt the new ai SDK resume semantics](adopt-the-new-ai-sdk-resume-semantics.md) - `ai` 6.0.250 made a resumed stream a fresh response, so the assistant client is pinned below it and two conformance cases fail on the current release.

## Known and accepted

Not backlog. Recorded as decisions because they were chosen, not deferred:

- [build_strategy is not revision-guarded](../decisions/build-strategy-is-not-revision-guarded.md)
- [No faker or msw generation](../decisions/no-faker-or-msw-generation.md)
- [The nested tree stays at the wire boundary](../decisions/nested-tree-at-the-wire-boundary.md)
