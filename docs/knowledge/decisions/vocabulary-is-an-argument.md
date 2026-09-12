---
type: Decision
title: The runtime takes the vocabulary as an argument; the wire keeps it
description: Batch C turned roles, guard tool-name sets, instruction renderers and memory kinds into arguments the product supplies, and left the published enums narrow until a second assistant needed other values. The role enums are open now that one does; MemoryValue.kind keeps its enum.
tags: [assistant-core, ws2, transport, openapi]
generated: { by: claude-code/opus-5, at: 2026-08-21T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-21T00:00:00Z }
status: stable
---

# What was found

Batch C had to remove PathFinder's vocabulary from the runtime: the four
phase roles, the tool names the guards key on, the strategy instruction
renderers, and the four memory kinds. Most of that vocabulary is only read
in-process, and moving it to a constructor argument or an explicit import
costs nothing.

Three of those names are also published. `ChatRequestBody.phaseModels` and
`ChatRequestBody.phaseReasoning` carried `propertyNames.enum`,
`ModelListResponse.phaseDefaults` carried the same enum, `TierPreset` had one
required property per role, and `MemoryValue.kind` is an enum inside every
`/api/v1/memories` response. Those schemas are generated into
`packages/shared-ts`, and the web app passes a memory's `kind` straight back
into the `kind` query parameter, so widening a response to a plain string is a
change the frontend has to absorb.

The request boundary also refused an undeclared role with a Pydantic
`literal_error` at `("phaseModels", "<key>", "[key]")`. A validator that
checks membership instead returns a `value_error` at a different location,
which is a different 422 body.

# The decision

The runtime types every role and kind as `str`.

`TurnContext.phase_models`, `TurnContext.phase_reasoning`,
`resolve_phase_tier_config`, the agent registry, `PendingApproval.phase` and
every memory store, retrieval and tombstone signature take a plain string.
`MemoryValue.kind` keeps its literal; the tombstone kind, which is not
published, is a plain string.

The published role enums stayed narrow until a second assistant published
other values, which is what the widening was waiting for. They are open now:
`phaseModels`, `phaseReasoning` and `phaseDefaults` carry plain role names, a
`TierPreset` is a mapping from a role name to its config, and a request naming
a role no installed assistant runs a model for is refused with a `value_error`
at `("phaseModels",)` rather than a `literal_error` at the key. The role set a
request is checked against is derived from the presets, so no second list can
drift from it.

# Anchor

`apps/api/src/pathfinder/ai/conversation/request_body.py` and
`platform/tiers.py` hold the role vocabulary the wire carries;
`assistant_core/memory/schemas.py` holds the memory one. Done if a kind literal
appears anywhere that `openapi.json` does not already publish, or if a second
list of role names appears beside the presets.
