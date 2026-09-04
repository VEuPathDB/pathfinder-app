Architecture Overview
=====================

This page describes the PathFinder backend as it is built: how one chat turn
travels from the HTTP route to the worker, what the Lead agent and its three
phase sub-agents do, and which layer is allowed to call which.

Installed Assistants
--------------------

The backend serves more than one assistant. An ``AssistantSpec`` supplies the
graph, the state and the context a turn needs; the registry says which specs
this deployment installs and which one answers when the request names none.

.. list-table:: Assistants
   :widths: 20 40 40
   :header-rows: 1

   * - Assistant
     - Graph
     - Scope
   * - **pathfinder**
     - ``lead`` then ``finalize_turn``
     - The default. Strategy construction, verification and EDA.
   * - **site_help**
     - ``agent`` then ``finalize_turn``
     - One agent, two catalog tools. No Lead, no ledger, no phases.

A conversation records its assistant. The request may name one only while the
thread is being created; naming a different one on an existing thread is
refused.

User-Facing Pages
-----------------

.. grid:: 2
   :gutter: 3

   .. grid-item-card:: Conversation
      :class-card: sd-border-primary

      ``/<siteId>/conversation/<conversationId>``. The chat thread, with the
      strategy graph and the EDA analysis as sibling routes. Uses
      ``POST /api/v1/chat``.

   .. grid-item-card:: Workbench
      :class-card: sd-border-success

      ``/<siteId>/workbench``. Gene set management, enrichment, distributions
      and cross-validation, backed by the experiment endpoints.
      See :doc:`gene_sets`.

The **experiment endpoints** (``/api/v1/experiments/...``) are the evaluation
engine the workbench consumes: control-set evaluation, classification metrics,
cross-validation and enrichment. See :doc:`experiments`.

How One Chat Turn Runs
----------------------

.. mermaid::

   flowchart TD
       A["POST /api/v1/chat"] --> B["Dispatcher<br/><small>resolve assistant, persist user message</small>"]
       B --> C["defer chat_turn job"]
       B --> S["SSE tail of conversation_events"]
       C --> W["Worker: turn runner"]
       W --> G["Turn graph: lead -> finalize_turn"]
       G --> L["Lead agent"]
       L --> F["FRAME"]
       L --> E["BUILD"]
       L --> V["VERIFY"]
       F --> LG["InvestigationLedger"]
       E --> LG
       V --> LG
       LG --> L
       L --> EV["conversation_events"]
       EV --> S

       style A fill:#2563eb,color:#fff
       style W fill:#7c3aed,color:#fff
       style L fill:#0891b2,color:#fff

1. ``POST /api/v1/chat`` reaches
   :py:mod:`pathfinder.ai.conversation.dispatcher`. It resolves the
   conversation's assistant, runs that assistant's identity gate, persists the
   user message, defers a ``chat_turn`` Procrastinate job and returns an SSE
   tail of the durable event log. **The API process never runs the agent.**
2. The worker consumes ``chat_turn`` and drives the graph the assistant's spec
   returns. Every turn is checkpointed with ``AsyncPostgresSaver``, so a thread
   survives a restart.
3. Each chunk the turn emits is written to ``conversation_events`` and tailed
   back to the client with ``LISTEN``/``NOTIFY``. Postgres is the only broker.

.. important::

   Chat turns run in the worker container. A chat request that hangs with no
   chunks is a worker that is not consuming the ``chat_turn`` queue.

Lead and the Phase Sub-agents
-----------------------------

PathFinder's graph has two nodes, ``lead`` and ``finalize_turn``. The Lead is
the only voice the user hears and the only LLM the graph itself runs. A phase
is a tool the Lead calls, not a node it hands control to.

.. list-table:: Phases
   :widths: 15 45 40
   :header-rows: 1

   * - Phase
     - What it does
     - Lead's tool
   * - **FRAME**
     - States the criteria and binds each one to a real search with resolved
       parameters. Proposes; never writes to WDK.
     - ``frame_problem``
   * - **BUILD**
     - Builds the strategy from the spec and applies atomic edits. The only
       agent that mutates the graph.
     - ``build_strategy``, ``edit_strategy``, ``recover_failed_steps``
   * - **VERIFY**
     - Control tests, parameter optimization, enrichment, variant comparison
       and export.
     - ``verify_strategy``, ``compare_search_variants``

Between calls the Lead reads
:py:class:`~pathfinder.ai.lead.ledger.InvestigationLedger`, the typed record of
what the turn established: the operational spec, the searches chosen, the
counts observed and the verification digest. It does not re-read sub-agent
transcripts. ``consult_user`` and ``clear_strategy`` require the user's
approval before they run.

See :doc:`agents` for each agent, :doc:`tools` for the toolsets and
:doc:`chat` for the transport.

Durable Tools
-------------

A tool that takes minutes does not block the turn. ``@durable_tool`` writes a
``background_tasks`` row, defers a Procrastinate job, emits
``data-background-task-started`` and raises ``CallDeferred``; the turn closes
with ``finishReason: "other"`` and one parked call checkpointed. The worker
runs the real implementation, reports progress on ``task_progress``, and opens
a **new turn** carrying the result. Nothing before the call runs again.

Turn Chunks
-----------

The turn speaks the Vercel AI SDK v6 UI Message Stream protocol. Beside the
protocol's own text, reasoning and tool parts, PathFinder emits typed
``data-*`` parts that the frontend renders as message content, among them:

.. list-table:: Typed data parts
   :widths: 40 60
   :header-rows: 1

   * - Part
     - Carries
   * - ``data-sub-agent-call`` / ``data-sub-agent-step``
     - Which phase is running and what it just did
   * - ``data-ledger-update``
     - The ledger after a phase returned
   * - ``data-graph-snapshot`` / ``data-strategy-link``
     - The strategy graph, and its WDK id and URL once saved
   * - ``data-background-task-started`` / ``data-task-progress`` /
       ``data-task-completed``
     - A durable tool's lifecycle
   * - ``data-enrichment-results``
     - What VERIFY established
   * - ``data-eda.analysis-state`` / ``data-eda.subset-preview`` /
       ``data-eda.viz``
     - The EDA analysis, its subset and its figure
   * - ``data-turn-usage`` / ``data-lead-usage``
     - Tokens and cost for the turn and for the Lead

The union of kinds the frontend knows is ``DataPartKind`` in
``@pathfinder/shared``. An unknown kind reaches the fallback renderer rather
than breaking the thread.

Cross-thread Memory
-------------------

Memories live in a pgvector-backed store under ``("user", user_id, kind)`` with
four kinds: ``gene_set``, ``strategy``, ``preference`` and ``knowledge``.
``finalize_turn`` writes automatically when the verification digest reports
success; ``knowledge`` is written only by the ``remember`` tool. The Lead and
every sub-agent get the retrieved memories as a dynamic instruction.

Architecture Layers
-------------------

.. mermaid::

   flowchart TD
       T["Transport<br/><small>FastAPI routers, SSE, schemas</small>"] --> S["Services<br/><small>Business logic orchestration</small>"]
       AT["AI tools<br/><small>thin wrappers</small>"] --> S
       S --> D["Domain<br/><small>Strategy AST, parameters - pure, no I/O</small>"]
       S --> I["Integrations<br/><small>WDK client, embeddings</small>"]
       S --> P["Persistence<br/><small>PostgreSQL repositories</small>"]

       style T fill:#2563eb,color:#fff
       style AT fill:#0891b2,color:#fff
       style S fill:#7c3aed,color:#fff
       style D fill:#059669,color:#fff
       style I fill:#d97706,color:#fff
       style P fill:#dc2626,color:#fff

**Key rules:**

- **Transport** handles HTTP and SSE only. It calls Services, never Domain or
  Integrations.
- **AI tools** are thin wrappers over Services. A tool that calls WDK directly
  is a layering break.
- **Services** orchestrate Domain, Integrations and Persistence.
- **Domain** is pure: no I/O, no side effects, no imports from other layers.
- **Integrations** are HTTP clients; business logic lives in Services.
- **Persistence** uses the repository pattern; services never write raw SQL.

The runtime itself lives outside ``pathfinder``. ``assistant_core`` is a
separate distribution that owns the graph scaffolding, the event log, the
checkpointer, the memory store and the settings, and it cannot import
``pathfinder``. Anything that names a gene, a strategy, a WDK search or a phase
role stays in ``pathfinder.ai``.

Design Decisions
~~~~~~~~~~~~~~~~

.. dropdown:: Why a Lead that calls phases as tools, instead of a phase graph?
   :class-title: sd-font-weight-bold

   A fixed graph of phases forces every turn through the same route, so
   "rename this step" pays for a framing pass. The Lead classifies the intent
   and calls only the phases the turn needs, and the ledger gives it a typed
   view of what each call established without re-reading transcripts.

.. dropdown:: Why does the API process not run the agent?
   :class-title: sd-font-weight-bold

   A turn outlives an HTTP connection. Deferring the work to a worker and
   returning a tail of the durable event log means the client can disconnect,
   reload or reconnect from a cursor, and the turn keeps running. It also
   keeps a slow LLM call off the request-serving event loop.

.. dropdown:: Why Postgres as the only broker?
   :class-title: sd-font-weight-bold

   ``conversation_events`` is already the source of truth for message parts,
   so history replay and live streaming read the same rows. ``LISTEN`` and
   ``NOTIFY`` deliver the wake-up. A second store would add a way for the
   stream and the transcript to disagree.

.. dropdown:: Why SSE instead of WebSocket?
   :class-title: sd-font-weight-bold

   The chat stream is unidirectional: the client posts a message and the
   server streams the turn. SSE needs no upgrade handshake, survives HTTP/1.1
   proxies and resumes from a cursor, which is what a durable event log wants.

See Also
--------

.. grid:: 2
   :gutter: 3

   .. grid-item-card:: Chat Pipeline
      :link: chat
      :link-type: doc

      Dispatcher, turn runner, turn graph and the durable event log.

   .. grid-item-card:: Agents
      :link: agents
      :link-type: doc

      Lead agent and the FRAME, BUILD and VERIFY sub-agents.

   .. grid-item-card:: AI Tools
      :link: tools
      :link-type: doc

      Every tool the agents can call, grouped by subject.

   .. grid-item-card:: Evaluation Engine
      :link: experiments
      :link-type: doc

      Experiment modes, execution, analysis and control sets.
