---
type: Decision
title: The orchestration belongs to the assistant, not to the platform
description: An assistant declares its own compiled graph, turn-state type, checkpoint types, stream parts, memory kinds, mock model, identity gate and turn epilogue on a frozen AssistantSpec that names no product; the runtime resolves one per turn from a registry keyed by the conversation row. One platform graph shape parameterized by config was rejected.
tags: [platform, assistant-spec, routing, identity, architecture]
generated: { by: claude-code/opus-5, at: 2026-08-22T00:00:00Z }
verified: { by: claude-code/opus-5, at: 2026-08-22T00:00:00Z }
status: stable
---

# What was decided

`assistant_core` owns turns, durability, streaming, checkpoints, memory,
approvals, guards, cost and identity *enforcement*. It owns no opinion about
what an assistant is made of.

**One frozen model carries the whole declaration.**
`assistant_core/spec.py::AssistantSpec` has `assistant_id` and eight
declarations: a graph factory (`checkpointer -> CompiledStateGraph`), an
initial-state factory (`TurnStart -> TurnState`), a turn-context factory
(`TurnContextRequest -> TurnContext`), a mock-model factory, `checkpoint_types`,
a stream-part registration hook, `memory_kinds`, an identity gate, and a turn
epilogue. Every one of them replaces something the pipeline previously
hard-coded about PathFinder. The spec module imports `persistence.models` and
`platform.types` and nothing else outside core; the pinned core-surface test
fails if that grows.

**The graph is a factory, not a shape.** The runtime never names a node, an
edge, a phase or an agent. PathFinder hands it a two-node lead graph over
`PipelineState`; an assistant with a single agent loop and a bare `TurnState`
hands it that, and the runtime cannot tell them apart.

**Partial state is preserved by construction.** The state factory returns a
model, and the runtime sends `{name: getattr(state, name) for name in
state.model_fields_set}` to the graph. A field the factory did not set keeps
its checkpointed value, so an approval resume does not blank the prompt the
checkpoint holds.

**The conversation row is the routing record.** `conversations.assistant_id`
is `NOT NULL DEFAULT 'pathfinder'` in the database, and that default answers
only a writer that omits the column in its SQL. The runtime's mapped default
names no product, so an insert through the model that does not name an
assistant writes `default`, which this registry does not install, so every
insert here names one: `ConversationRepository.create` takes a required
`assistant_id`, and a route that accepts an `assistantId` resolves it before it
writes. A new thread takes the request's
`assistantId` or the registry default; an existing thread keeps what it was
created with, and a request naming another one is refused **409
`ASSISTANT_MISMATCH`**, not ignored. An unknown id is **404
`ASSISTANT_NOT_FOUND`**. The row stays the authority after the insert too:
`dispatch` compares what `begin_conversation` returned against what it
resolved, so a concurrent first turn that created the thread under another
assistant is refused rather than deferred under the wrong one. The worker
resolves the spec from the id the payload carries, and the durable-task
resume reads it back off the row.

**Identity is per assistant, enforced in transport.** The chat route's
dependency resolves the assistant and then runs `spec.identity_gate` when the
assistant declares one. PathFinder declares
`services/wdk_identity.py::require_registered_wdk_login`, so its refusal is
the same 401 `WDK_LOGIN_REQUIRED` on the same route, byte for byte. An
assistant that declares no gate is served to any authenticated caller - the
application's own session auth still applies, because that is the runtime's,
not the assistant's.

**The checkpoint allowlist is the union.** One checkpoint table serves every
assistant, so `AssistantRegistry.checkpoint_types()` unions what the installed
specs declare and each process passes it to `lifespan_checkpointer`. The
import-time `register_checkpoint_types` accumulator is gone: a declaration
that only takes effect if some module was imported first is not a declaration.

# What was rejected

**One platform graph shape, parameterized by config.** Keep a single
`StateGraph` in core - lead node plus finalize node - and let each assistant
switch parts of it off: no sub-agents, no ledger, one tool set. It is the
smaller diff and it reuses the streaming and approval plumbing that already
hangs off those nodes.

It was rejected because a config-shaped Lead is still a Lead. Every assistant
would inherit a turn structure built for multi-phase strategy work: a
supervisor step it does not need, a state slot it leaves empty, a dispatch
vocabulary it never uses, and a set of switches that only make sense to
someone who knows PathFinder. The cost lands twice - on the simple assistant,
which pays orchestration it did not ask for, and on the runtime, which cannot
change the lead shape without breaking assistants that never used it. A
factory returning a compiled graph costs one field and lets the simple
assistant's diff contain no orchestration at all, which is the measurable form
of the claim.

**A single `Assistant` base class to subclass.** Inheritance would let core
call `self.build_graph()`, but it also lets core add a method that every
assistant must then implement, and it puts product code in core's type
hierarchy. Composition over inheritance: the spec holds callables.

**An `IdentityRequirement` enum resolved through a lookup table.** A named
requirement (`"registered_wdk_login"`) mapped to a dependency in transport
would keep core free of WDK, but it buys an indirection with exactly one
entry, and the table becomes a second place to keep in sync. The spec carries
the async callable that raises; core never learns what it checks.

**Ignoring a mismatched `assistantId` after an equality check.** Silently
serving the thread's assistant would keep old clients working, but a caller
that believes it is talking to assistant B and reads assistant A's answers has
no way to notice. The thread still never changes assistant either way; only
the loud refusal tells the caller its assumption was wrong.

# What the pilot added

A second assistant now exists, so every creation path carries the choice.
`POST /api/v1/conversations/{id}/begin` and `POST /api/v1/conversations/open`
take an optional `assistantId` with the same semantics as chat, and the begin
route's seed-title generation uses that assistant's mock rather than the
default's; `devtools/chat.py` takes `--assistant`.

The runtime gained a stock graph for the simple case:
`assistant_core/graph/single_agent.py::single_agent_graph`, an agent node plus
the runtime's finalize node, usable by any assistant whose turn is one agent.
It is a helper an assistant may take, not a shape the runtime imposes - the
spec still carries a factory, and PathFinder does not use it.

**The finalize step is a second node, not the tail of the first.** The
assistant message row is reduced from the chunks the durable log holds for the
turn, and the log only holds them once the agent's step has ended and the
stream consumer has written them. A finalize inside the agent node would read
an incomplete log and write a message with no parts.

**How a turn is charged stays product-side.** The arithmetic is the runtime's
(`assistant_core.quota`), but the budget and the moment of charge are the
product's, so `single_agent_graph` takes the charger as a required hook. An
assistant that does not state how its turns are charged does not compile.

# What this does not decide

Per-assistant budgets, namespaced part kinds, and publishing the assistant
roster on the wire all wait for the client that consumes them. Frontend
assistant selection waits for a second UI.
