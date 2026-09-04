HTTP Transport
==============

FastAPI dependencies, SSE streaming, and HTTP-layer utilities. Connects
the HTTP API to the chat and strategy services.

Overview
--------

- **Dependencies** — Request-scoped deps: auth, DB session, repository injection.
  Injected into router handlers.
- **Streaming** — SSE (Server-Sent Events) for chat. Event formatting,
  chunk encoding, stream lifecycle.

Application Factory
-------------------

**Purpose:** FastAPI application entrypoint. Creates the app with middleware,
lifecycle management (database init, Redis), router registration, and
startup background tasks.

**Design:** The factory pattern (``create_app()``) enables testing with different
configurations and ensures clean setup/teardown of database connections and Redis
pools via FastAPI lifespan events.

.. automodule:: pathfinder.main
   :members:
   :undoc-members:
   :show-inheritance:

Developer Tools
---------------

**Purpose:** Developer tooling for keeping the OpenAPI spec in sync with the
FastAPI application. Generates ``packages/spec/openapi.yaml`` and
``packages/shared-ts/src/openapi.generated.ts`` from the running app's schema.
This is intentionally NOT run at runtime — it writes repo files during
development.

.. automodule:: pathfinder.devtools.openapi
   :members:
   :undoc-members:
   :show-inheritance:

Dependencies
------------

**Purpose:** FastAPI dependencies. Provide auth context, DB session, repository
injection, and experiment ownership checks. Used by routers.

**Key functions:** :py:func:`get_current_user_with_db_row`,
:py:func:`get_experiment_owned_by_user`

.. automodule:: pathfinder.transport.http.deps
   :members:
   :undoc-members:
   :show-inheritance:

SSE Helpers
-----------

**Purpose:** Format a typed event as an SSE frame for the experiment, sweep
and seed progress streams. Conversation does not use these; it goes through
the LangGraph stream-event pipeline.

.. automodule:: pathfinder.transport.http.sse_utils
   :members:
   :undoc-members:
   :show-inheritance:

Routers
-------

FastAPI routers that define the HTTP API surface. Each router handles a
specific domain area.

.. automodule:: pathfinder.transport.http.routers.chat
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.sites.catalog
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.sites.genes
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.sites.params
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.models
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.health
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.control_sets
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.veupathdb_auth
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.dev
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.exports
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.gene_sets.crud
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.gene_sets.operations
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.gene_sets.enrichment
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.gene_sets.records
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.gene_sets.confidence
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.conversations.operations
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.user_data
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.conversations.crud
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.conversations.counts
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.conversations.wdk_import
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.experiments.execution
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.experiments.evaluation
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.experiments.enrichment
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.routers.experiments.results
   :members:
   :undoc-members:
   :show-inheritance:

Schemas
-------

Pydantic request/response models (DTOs) for the HTTP API.

.. automodule:: pathfinder.transport.http.schemas.conversations
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.schemas.sites
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.schemas.steps
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.schemas.experiments
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.schemas.health
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.schemas.veupathdb_auth
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.transport.http.schemas.gene_sets
   :members:
   :undoc-members:
   :show-inheritance:

