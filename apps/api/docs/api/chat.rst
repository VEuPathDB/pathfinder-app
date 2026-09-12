Chat Pipeline
=============

How one chat turn runs: the HTTP route defers the work, the worker drives a
LangGraph turn, and every chunk the turn emits is written to
``conversation_events`` and tailed back over SSE.

.. mermaid::

   sequenceDiagram
       participant Client
       participant Router
       participant Dispatcher
       participant Worker
       participant Lead

       Client->>Router: POST /api/v1/chat
       Router->>Dispatcher: resolve assistant, persist user message
       Dispatcher->>Worker: defer chat_turn job
       Dispatcher-->>Client: SSE tail of conversation_events
       Worker->>Lead: run the turn graph
       loop Streaming
           Lead->>Lead: sub-agent tool call
           Lead-->>Worker: chunk
           Worker-->>Client: persisted chunk over SSE
       end

Overview
--------

- **Dispatcher** — Resolve the assistant, persist the user message, defer the
  turn to the worker, and return the SSE tail. The API process never runs the
  agent.
- **Turn Runner** — The worker side. Drives the assistant's graph and closes
  the turn.
- **Turn Graph** — A two-node ``StateGraph``: ``lead`` then ``finalize_turn``.
- **Stream Events** — The typed ``data-*`` chunks the turn emits.
- **Event Log** — Every chunk is a row in ``conversation_events``, replayed
  for history and for reconnect.

.. important::

   Chat turns run in the worker container, not in the API process. A chat
   request that hangs with no chunks is a worker that is not consuming the
   ``chat_turn`` queue.

Dispatcher
----------

**Purpose:** Entry point for a chat turn. Resolves the conversation's
assistant, runs its identity gate, persists the user message, defers the
``chat_turn`` job, and returns the durable event tail.

.. automodule:: pathfinder.ai.conversation.dispatcher
   :members:
   :undoc-members:
   :show-inheritance:

Request Body
------------

**Purpose:** The chat request DTO. Parses the AI SDK message list and strips
the parts a resend must not replay.

.. automodule:: pathfinder.ai.conversation.request_body
   :members:
   :undoc-members:
   :show-inheritance:

Turn Runner
-----------

**Purpose:** The worker side of a turn. Builds the graph the assistant's spec
returns, streams its chunks into the event writer, and finalizes the turn.

.. automodule:: pathfinder.ai.conversation.turn_runner
   :members:
   :undoc-members:
   :show-inheritance:

Turn Stop
---------

**Purpose:** Cancel a running turn. The cancel path closes every open tool
call so no trace row reads as running forever.

.. automodule:: pathfinder.ai.conversation.turn_stop
   :members:
   :undoc-members:
   :show-inheritance:

Title Generation
----------------

**Purpose:** Name a conversation from its first user message, using the
provider's smallest model.

.. automodule:: pathfinder.ai.conversation.title_generator
   :members:
   :undoc-members:
   :show-inheritance:

Turn Graph
----------

**Purpose:** PathFinder's turn graph: ``lead`` then ``finalize_turn``. The
Lead node runs the only LLM in the graph; the sub-agents are tools it calls.

.. automodule:: pathfinder.ai.graph.builder
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.graph.lead_node
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.graph.nodes
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.graph.state
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.graph.runtime
   :members:
   :undoc-members:
   :show-inheritance:

Stream Events
-------------

**Purpose:** Build the typed ``data-*`` chunks that carry strategy and EDA
telemetry to the frontend as parts on the assistant message.

.. automodule:: pathfinder.ai.graph.stream_events
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.strategy_stream_parts
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.eda_stream_parts
   :members:
   :undoc-members:
   :show-inheritance:

Durable Event Log
-----------------

**Purpose:** The runtime's side of the pipeline: translate agent events into
AI SDK chunks, write each chunk to ``conversation_events``, and tail the log
over SSE with LISTEN/NOTIFY. Owned by the ``assistant_core`` package.

.. automodule:: assistant_core.conversation.vercel_adapter
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: assistant_core.conversation.event_writer
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: assistant_core.conversation.event_stream
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: assistant_core.conversation.ui_message_reducer
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: assistant_core.conversation.checkpointer
   :members:
   :undoc-members:
   :show-inheritance:
