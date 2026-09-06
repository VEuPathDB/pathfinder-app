---
type: Decision
title: The runtime's part payloads live in the runtime, so the package builds alone
description: The three durable-task payloads and TurnUsage moved from the product's shared model package into assistant_core/conversation/stream_parts/, and assistant-core dropped its dependency on that package. Publishing the shared package as a second distribution was rejected, because it had no second consumer and would make a host install PathFinder's product models to run a turn.
tags: [assistant-core, packaging, stream-parts, protocol]
generated: { by: claude-code/opus-5, at: 2026-08-25T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-25T00:00:00Z }
status: stable
---

# What was decided

`assistant-core` declares no dependency on any package of PathFinder's. The two
modules it read from the product's shared model package are payload declarations
for parts the runtime itself emits, so they are the runtime's:
`BackgroundTaskStarted`, `TaskProgress` and `TaskCompleted` are now
`assistant_core/conversation/stream_parts/task_parts.py`, and
`TurnUsage` is `.../stream_parts/turn_usage.py`. The class names did not
change, because `PROTOCOL.md` names them and the OpenAPI schema index
publishes them.

They rebased from `shared_py.pydantic_base.CamelModel` onto
`assistant_core.platform.pydantic_base.CamelModel`. The two bases differ by one
key, `extra="ignore"`, which is Pydantic's own default, so the wire behaviour
and the published schema are unchanged.

`pathfinder-shared` is gone. The models that name a gene, a strategy or an
enrichment folded into `apps/api`: the part payloads are
`pathfinder/ai/stream_part_payloads.py` and `pathfinder/domain/eda_parts.py`,
and no distribution outside `apps/api` declares them.

# What was rejected

**Publishing `pathfinder-shared` as a second distribution.** It is the smaller
edit: leave the modules, add a build target. It was rejected because the
package has no second consumer and its remaining contents are PathFinder's
product parts. A host that wants to run a turn would install a distribution of
gene-set and strategy payloads to get four models it does emit, and the runtime
would carry the product's release cadence.

**A re-export shim in `shared_py`.** Rejected on the no-backwards-compat rule.
Nothing outside the runtime imported either module, so the move has no
migration cost to defer.

# What the move cost

The payload modules could not go under `conversation/stream_parts/` while that
package's `__init__.py` built the registry, because
`graph/stream_events.py` constructs `TaskProgress` and `TaskCompleted`, and
`core_parts.py` reads six payload classes back out of `graph/stream_events.py`.
Importing `assistant_core.graph.stream_events` first would run the package
`__init__`, which would re-enter a module that is half executed, and the second
import fails with a partially initialized module.

So `__init__.py` imports nothing and `STREAM_PARTS` lives in `core_parts.py`
beside the registrations it holds. A package that runs imports on load cannot
hold a module that its own importers need, and the failure depends on which
module a process reaches first, which is the worst kind.

# What would falsify this

`cd assistant-platform/packages/assistant-core && uv build`, then installing the wheel into a
venv with no path dependencies and importing
`assistant_core.graph.stream_events`: the day that needs a module of
PathFinder's, this is gone. `assistant-platform/packages/assistant-core/tests/unit/test_package_boundary.py` fails if any
module under `assistant_core` imports `pathfinder`, and pins the two payload
modules to the model library alone.
