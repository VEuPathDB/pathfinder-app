Platform
========

Shared infrastructure: config, types, errors, security, and logging.
Used throughout the application. No business logic.

Overview
--------

- **Config** — Application settings (API keys, database URL, feature flags).
  Loaded from environment and .env files.
- **Types** — Shared type aliases: JSONObject, JSONArray, JSONValue.
- **Errors** — WDKError, ValidationError, ErrorCode. Consistent error handling.
- **Security** — Auth and authorization helpers.
- **Logging** — Structured logging setup.

Design Decisions
~~~~~~~~~~~~~~~~

.. dropdown:: PostgreSQL as the only broker
   :icon: broadcast

   Durable events are rows in ``conversation_events`` and
   ``task_progress``, published with ``pg_notify`` and tailed with
   LISTEN/NOTIFY. One store means a client can replay from a cursor after a
   restart without a second system to keep in step.

.. dropdown:: Pydantic settings
   :icon: gear

   Configuration uses ``pydantic-settings`` with TOML +
   environment variable layering. TOML provides checked-in defaults; environment
   variables override for deployment. This avoids the "which .env file?" problem
   while keeping sensitive values out of version control.

.. dropdown:: Structured logging via structlog
   :icon: log

   All logging uses ``structlog`` with JSON
   output. This enables structured queries in log aggregation tools (filtering by
   ``user_id``, ``strategy_id``, ``tool_name``) without string parsing. Development
   mode uses human-readable console output.

.. dropdown:: Context variables for request state
   :icon: link

   Request-scoped state (auth token, user
   ID, site context) propagates via Python ``contextvars``. This avoids threading
   state through every function signature while remaining async-safe (each task
   gets its own context copy).

.. tip::

   All configuration values can be overridden via environment variables.
   See ``config.toml`` for defaults and ``platform/config.py`` for the
   full settings schema.

Config
------

**Purpose:** Application settings. API keys (OpenAI, Anthropic, etc.), database
URL, and feature flags. Loaded via pydantic-settings.

**Key function:** :py:func:`get_settings`

.. automodule:: pathfinder.platform.config
   :members:
   :undoc-members:
   :show-inheritance:

Types
-----

**Purpose:** Shared type aliases for untyped dict/list payloads. JSONObject,
JSONArray, JSONValue. Owned by the runtime package and used throughout.

.. automodule:: assistant_core.platform.types
   :members:
   :undoc-members:
   :show-inheritance:

Errors
------

**Purpose:** PathFinder's own exception types, the wire's ``ErrorCode`` enum and
the ``ProblemDetail`` body. A VEuPathDB refusal lives in
``veupathdb.errors`` and reaches the wire through
:py:func:`veupathdb_error_handler`.

**Key classes:** :py:class:`AppError`, :py:class:`ProblemDetail`

.. automodule:: pathfinder.platform.errors
   :members:
   :undoc-members:
   :show-inheritance:

Security
--------

**Purpose:** Authentication and authorization. Token validation, permission
checks, user context. Used by HTTP deps and routers.

.. automodule:: pathfinder.platform.security
   :members:
   :undoc-members:
   :show-inheritance:

Logging
-------

**Purpose:** Structured logging. get_logger returns a logger configured for
JSON/structlog output. Used by all modules.

**Key function:** :py:func:`get_logger`

.. automodule:: assistant_core.platform.logging
   :members:
   :undoc-members:
   :show-inheritance:

Context
-------

**Purpose:** Context variables for request-scoped state. The request base URL
and this turn's model picks; the runtime package and the client library own the
rest.

.. automodule:: pathfinder.platform.context
   :members:
   :undoc-members:
   :show-inheritance:

Notify Dispatcher
-----------------

**Purpose:** Fan a PostgreSQL ``LISTEN`` connection out to the subscribers
waiting on one channel.

.. automodule:: pathfinder.platform.notify_dispatcher
   :members:
   :undoc-members:
   :show-inheritance:

Health
------

**Purpose:** Health check logic and readiness probe implementation.

.. automodule:: pathfinder.platform.health
   :members:
   :undoc-members:
   :show-inheritance:

Store
-----

**Purpose:** Generic store abstractions for in-memory + persistence patterns.

.. automodule:: pathfinder.platform.store
   :members:
   :undoc-members:
   :show-inheritance:

Tasks
-----

**Purpose:** Background task infrastructure and management.

.. automodule:: pathfinder.platform.tasks
   :members:
   :undoc-members:
   :show-inheritance:

