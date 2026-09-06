---
type: Decision
title: A boolean operator is a type, not a string
description: CombineOp narrowed to WDK's boolean set is a reusable annotated type, so an invalid operator is a 422 rather than an opaque WDK error.
tags: [strategy-graph, types, wdk-alignment]
generated: { by: claude-code/opus-5, at: 2026-08-09T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-09T00:00:00Z }
status: stable
---

# What prompted it

`create_combined_step` was the last step-creation method taking loose arguments, which is why it carried a `PLR0913` noqa while `create_step` and `create_transform_step` already took a `NewStepSpec`. Giving it a `CombinedStepSpec` raised the question its old signature had hidden: what type is `boolean_operator`?

It was `str`, everywhere, from the HTTP request body and the AI tool argument all the way into WDK's boolean search config. A typo reached VEuPathDB and came back as an opaque service error.

# The subtlety

`CombineOp` is not the answer on its own. COLOCATE is a legitimate `CombineOp`, but not a boolean one: WDK does colocation through GenesBySpanLogic. So the constraint is per-usage, and the first cut duplicated it, once in the spec model and once at the HTTP boundary.

The rule is stated once instead, as a type:

```python
BOOLEAN_OPERATORS = frozenset(CombineOp) - {CombineOp.COLOCATE}
BooleanOperator = Annotated[CombineOp, AfterValidator(_must_be_boolean)]
```

Every field whose value ends up in a boolean search config uses `BooleanOperator`. Places that legitimately handle colocation, like experiment materialization, keep the wider `CombineOp` and branch on it.

# What it bought

* An unknown operator is a **422** at the edge instead of a WDK error mid-strategy.
* The AI tool argument is an enum in the tool schema, so the model cannot invent an operator; it gets a retry instead.
* `get_wdk_operator` was deleted. Its only remaining caller was converting an enum to a string purely to have it coerced back, and its COLOCATE guard is now the type's job.

# Anchor

`veupathdb-py/src/veupathdb/domain/strategy/ops.py` owns `BOOLEAN_OPERATORS` and `BooleanOperator`. Guarded by `veupathdb-py/tests/unit/wdk/test_wdk_models.py` and the two refine-route tests in `tests/integration/transport/test_experiment_results_routes.py`.
