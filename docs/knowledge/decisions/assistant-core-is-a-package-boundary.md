---
type: Decision
title: The assistant runtime is a package boundary, not a contract over scattered modules
description: The runtime-generic modules moved into pathfinder/assistant_core/ and an import-linter contract rejects any chain from there to the science; leaving the modules where they were and writing the contract over a module list was rejected, because it makes the future service extraction an archaeology exercise instead of a move.
tags: [assistant-core, ws2, architecture, import-linter]
generated: { by: claude-code/opus-5, at: 2026-08-22T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-22T00:00:00Z }
status: superseded
---

> Superseded by [the runtime is a package](the-runtime-is-a-package.md):
> the directory became `assistant-platform/packages/assistant-core`, and contract 7 became the
> package's own dependency list. What follows is why the directory came first.

# What was found

Batches A through C separated the assistant runtime from PathFinder's science by
type and by wiring, and left every file where it was. The result was a runtime
whose membership existed only in reviewers' heads: `ai/memory/` imported no
product module, `ai/graph/turn_state.py` held the generic turn, and nothing in
the tree said so. A directory listing of `ai/` gave a reader no way to tell the
half a second assistant reuses from the half that knows what a gene is.

The program's stated goal is that extracting the runtime as a service becomes a
packaging exercise. That goal is a claim about a directory, and there was no
directory.

# The decision

The runtime-generic modules moved into `apps/api/src/pathfinder/assistant_core/`
(`capabilities/`, `conversation/`, `graph/`, `memory/`, `models/`), and
import-linter contract 7 forbids any import chain from `pathfinder.assistant_core`
to `pathfinder.ai`, `pathfinder.domain`, `veupathdb.wdk`,
`pathfinder.services`, `pathfinder.transport`, `pathfinder.jobs` or
`pathfinder.devtools`. What is left reachable is the whole allowed surface:
`pathfinder.platform`, `pathfinder.persistence.models`, and
`veupathdb_mcp.embeddings`.

Contract 7 is the only one of the seven that also rejects indirect chains. The
other six are direct-only because they police layer discipline in a tree where
transitive reach is unavoidable: transport legitimately reaches integrations
through services. Contract 7 polices extractability instead, and a runtime that
reaches the science through one hop is not a runtime a second assistant can
take, so a direct-only version of it would assert nothing.

The rejected alternative was to write the contract over a list of modules and
leave them where they are. It costs nothing today and it fails at the moment it
matters: extracting the runtime would mean walking a 100-file `ai/` tree and
re-deriving, per file, which side it belongs to. A boundary that is only a
config entry is a boundary that has to be discovered again every time.

# What the boundary cost

Three modules had to be split along the line batch A already drew, because each
held both halves in one file: `ai/graph/runtime.py` (`TurnContext` and
`AssistantDeps` to core, `Context` and `AgentDeps` product),
`ai/graph/stream_events.py` (the runtime chunk builders to core, enrichment,
strategy revision and ledger to product), and
`veupathdb_mcp/embeddings/semantic_index.py`, whose embedding model was the
runtime's one indirect route to a WDK type and moved into the runtime's own
`embeddings/` package.

`PreTurnHook` and `TurnAgentFactory` became generic aliases parameterized by the
state, context and agent types, so core states the hook shape and the product
supplies `PipelineState`, `Context` and `LeadAgent` at the call.

`ai/graph/builder.py` did not move. It names `make_lead_node` and
`finalize_turn_node` directly, and injecting a graph's node set is a seam this
batch did not design. Contract 7 is what will refuse it entry until that seam
exists.

# Anchor

`apps/api/pyproject.toml` holds contract 7;
`apps/api/src/pathfinder/tests/unit/test_core_boundary.py` pins
the allowed surface so it cannot grow unnoticed. Done if a module under
`assistant_core/` names a gene, a strategy, a WDK search or a phase role.
