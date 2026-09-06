---
type: Decision
title: The nested tree stays at the wire boundary
description: R1 separated step data from tree structure in memory but deliberately kept StrategyAst nested for persistence and the wire.
tags: [strategy-graph, wdk-alignment, r1]
generated: { by: claude-code/opus-5, at: 2026-08-09T00:00:00Z }
verified: { by: human:ahmedOmuharram, at: 2026-08-09T00:00:00Z }
status: stable
---

# The apparent conflict

`CLAUDE.md` lists "step trees: primary + secondary inputs (not flattened to lists)" as non-negotiable, which reads like it forbids R1 outright.

It does not, and resolving that is the whole decision. WDK's own `StrategyDetails` holds structure and data **separately**:

```typescript
stepTree: StepTree; // nested, carries only stepId
steps: Record<number, Step>; // the data
```

`StrategyStepNode` conflated the two by nesting whole nodes inside `primaryInput` and `secondaryInput`. That conflation **is** the aliasing bug: `StrategyGraph.steps` indexed the same objects the tree held, so an in-place edit changed both views, `apply_and_commit` needed a defensive deep copy to notice a change at all, and a half-applied batch corrupted the graph.

So R1 keeps the nested tree, which is required, and stops it carrying the payload. That is a move toward WDK, not away from it.

# What was rejected

Flattening the persisted `StrategyAst` too. It was rejected because nesting is what WDK's `stepTree` actually is, and because no data migration is needed if the boundary shape does not change. The nested form is now rebuilt only when projecting to WDK, via `rebuild_tree`.

# Evidence it was right

The frontend needed **zero** changes: it already read `Step.primaryInputStepId`. A divergence would have shown up there immediately. 1857 frontend tests passed untouched.

# Anchor

`veupathdb-py: src/veupathdb/domain/strategy/graph_model.py` (`flatten_tree` / `rebuild_tree`, proven by a Hypothesis round-trip over 200 generated trees) and `strategy_ast.py`, which stays nested.
