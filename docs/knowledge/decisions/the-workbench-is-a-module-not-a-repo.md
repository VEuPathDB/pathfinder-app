---
type: Decision
title: The workbench is a module, not a repository
description: features/analysis moved inside features/workbench and the merged feature publishes two entry paths that check-boundaries rule 6 enforces; pathfinder/services/workbench/ is a facade of functions that import-linter contract 8 makes the only way pathfinder.ai and pathfinder.jobs reach the workbench services. A separate repository now, and leaving the two features apart, were both rejected on measured numbers.
tags: [workbench, architecture, import-linter, boundaries, frontend, split]
generated: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-09-05T00:00:00Z }
status: superseded
---

> Superseded in v0.2.0a15: the workbench feature and its pages are gone
> ([VERIFY shows its evidence](verify-shows-its-evidence.md)). `FEATURE_ENTRYPOINTS`
> and rule 6 left `check-boundaries.mjs` with the only feature that published entry
> paths. The backend facade stays as `services/evidence/`, and contract five no
> longer names `services.gene_sets.enrichment`.

# The question

Should the workbench be its own repository?

# What was measured

Before the change, on this tree:

| edge | measured |
| --- | ---: |
| `features/workbench` and `features/conversation` naming `@/features/analysis` | 8 lines (7 workbench, 1 conversation) |
| files outside `features/workbench` naming `@/features/workbench` | 7 lines (6 route files, 1 conversation) |
| `features/workbench` naming `@/features/conversation` | 1 line, a `vi.mock` specifier in a test |
| `pathfinder/ai` and `pathfinder/jobs` naming a workbench service module | 24 lines in 12 files |

`features/analysis` is 78 files and imports no other feature. One of the seven
workbench edges named a file inside it, `@/features/analysis/components/ResultsTable`,
which is what an exception row admits when it names a feature and not a path.

Of the 24 backend lines, 9 named behaviour (a store, a sweep, an enrichment run,
a control-set service) and 15 named a result type.

# What was decided

**The workbench is one module with two enforced boundaries.**

`src/features/analysis/**` is `src/features/workbench/analysis/**`. The
`["workbench", new Set(["analysis"])]` exception row is gone, because there is
no longer a second feature to except.

`scripts/check-boundaries.mjs` gained `FEATURE_ENTRYPOINTS` and rule 6: a feature
that publishes entry paths is reachable through them and nothing else. Naming one
is the permission, so `"workbench"` left the `conversation` exception row as well:
`conversation -> @/features/workbench/api/geneSets` passes on the entry path, and
`conversation -> @/features/workbench/components/panels/BatchPanel` fails. A
feature absent from the map is closed by rule 1 unless an exception row admits it,
and an exception row admits a whole tree, which is why a feature with an API
belongs in the entry-path map instead. The checker's core is a
`checkSource(source, path)` function with its own `node --test` suite, run by
pre-commit and CI beside the check itself.

`pathfinder/services/evidence/` is the backend's entry, and it holds functions
with bodies, never `from X import Y` lines. That is the shape
[the WDK service layer](the-wdk-service-layer-holds-functions-not-re-exports.md)
already chose, and the reason the no-re-export rule does not block it. A result
type is still imported from the module that defines it: a facade that re-exports
a type is a re-export.

Import-linter contract 8 (the fifth contract in the file) is
`source_modules = ["pathfinder.ai", "pathfinder.jobs"]`, direct-only, forbidding
the modules whose behaviour the facade owns:
`services.control_sets`, `services.experiment.control_sourcing`,
`services.gene_sets.enrichment`, `services.gene_sets.store`,
`services.parameter_optimization.sweep`, `services.parameter_optimization.tunable`.

Two consequences the facade forced:

- `SweepTarget` and `SweepControls` moved from `parameter_optimization/sweep.py`
  to `parameter_optimization/config.py`, beside the other sweep value types, so
  the worker impl can name them without naming the forbidden module.
- Creating a control set is two facade functions, `new_control_set` (the input)
  and `create_control_set` (the write), because one function carrying all seven
  values exceeds the project's argument limit and grouping them is what the
  input model already does.

# What was rejected

**A repository of its own, now.** A repository is worth its cost when a second
consumer exists or a deployment needs a second container. Neither does. The
workbench reads `state/useWorkbenchStore.ts` from 24 files and three routes, and
its backend half sits on the same database and the same session factory as the
rest of `apps/api`. Splitting it today buys a second lockfile, a second CI lane
and a published API surface for one consumer.

**Leaving the two features apart.** The exception row said `workbench` may
import `analysis`, which is not a boundary: it admitted every file in the tree,
and one import had already reached a component two directories deep. Two
features with a one-way, unrestricted edge are one feature with a directory
separator in the middle.

**A facade of re-export lines.** Named in
[the WDK service layer decision](the-wdk-service-layer-holds-functions-not-re-exports.md):
an alias satisfies the contract while handing the caller the object the contract
exists to hide.

# What would reopen it

A second consumer of the workbench API, or a deployment that needs the workbench
in a container of its own. Either makes the published surface something other
than an internal convention, and the entry-path list plus the facade's function
list are already the surface such a split would start from.
