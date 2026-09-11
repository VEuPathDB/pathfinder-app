---
type: Decision
title: Step status is derived, never stored
description: StepStatus is computed from wiring, WDK id and validation on every read, against the task's original wording, and has four states rather than three.
tags: [strategy-graph, r2]
generated: { by: claude-code/opus-5, at: 2026-08-09T00:00:00Z }
verified: { by: human:ahmedOmuharram, at: 2026-08-09T00:00:00Z }
status: stable
---

# The problem it replaced

"What state is this step in" was answered in four places and answered differently: `is_built` from a WDK id, `defer_incomplete_new_steps` inferring draft from "validation failed AND never pushed", `is_computable` from the wiring, and the client's own `isBuilt: false`. That inference produced a live 422.

`step_status()` in `pathfinder/domain/strategy/step_status.py` is now the single answer.

# Derived, not stored

The original task said to store it. That was rejected: a stored copy is the same shape of bug as the stale step counts. It needs updating at every push, every parameter edit and every rewire, and one missed path leaves a step claiming to be built when it is not. `is_built` was already derived from `wdk_step_id is not None`; this follows that precedent.

# Four states, not three

The first cut had DRAFT, BUILT and INVALID. A test caught the hole immediately: a step that is complete but **not pushed yet** was classified DRAFT and would therefore be deferred forever, since pushing is exactly how a step stops being unbuilt. READY is that state. `is_pushable` is `not DRAFT`.

The old inference also missed the structural case entirely: a combine that has lost an input has every parameter it needs and still is not computable.

# Preserved deliberately

A step already live in WDK is never demoted to draft. `_validate_plan_params` re-raises for those, because silently turning a live step into a draft drops it from the built strategy.

# Anchor

`step_status()` and `StepStatus` in `apps/api/src/pathfinder/domain/strategy/step_status.py`;
`defer_draft_steps`, which replaced `defer_incomplete_new_steps`.

The lifecycle is this application's, not WDK's: the derivation reads the keyed
step map and the validation bundle from the client
(`veupathdb-py: src/veupathdb/domain/strategy/graph_model.py`,
`veupathdb-py: src/veupathdb/domain/strategy/validation.py`) and states a build
state no WDK endpoint answers.
