---
type: Decision
title: The runtime takes the vocabulary as an argument; the wire keeps it
description: Batch C turned roles, guard tool-name sets, instruction renderers and memory kinds into arguments the product supplies, but left the enums that are already published in openapi.json narrow, because widening a response enum is a client-visible change with no caller today.
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
`ChatRequestBody.phaseReasoning` carry `propertyNames.enum`, `ModelListResponse.phaseDefaults`
carries the same enum, `TierPreset` has one required property per role, and
`MemoryValue.kind` is an enum inside every `/api/v1/memories` response. Those
schemas are generated into `packages/shared-ts`, and the web app passes a
memory's `kind` straight back into the `kind` query parameter, so widening
the response to a plain string is a change the frontend has to absorb.

The request boundary also refuses an undeclared role with a Pydantic
`literal_error` at `("phaseModels", "<key>", "[key]")`. A validator that
checks membership instead returns a `value_error` at a different location,
which is a different 422 body.

# The decision

The runtime types every role and kind as `str`. The published models keep
their enums, and each names the product set it validates against.

`TurnContext.phase_models`, `TurnContext.phase_reasoning`,
`resolve_phase_tier_config`, the agent registry, `PendingApproval.phase` and
every memory store, retrieval and tombstone signature take a plain string. The
product's `PhaseRole` literal stays in `ai/agents/roles.py` and is imported by
exactly the three published models plus the devtools that build a request.
`MemoryValue.kind` keeps its literal; the tombstone kind, which is not
published, is a plain string.

The rejected alternative is widening the published enums now. It buys nothing
until a second assistant exists to publish other values, and it costs the 422
shape, the generated TypeScript unions, and a frontend change with no feature
behind it. WS3 opens them together with the client that needs them.

# Anchor

`apps/api/src/pathfinder/ai/conversation/request_body.py` and
`transport/http/routers/models.py` hold the two role-typed wire models;
`assistant_core/memory/schemas.py` holds the memory one. Done if a role or kind literal
appears anywhere that `openapi.json` does not already publish.
