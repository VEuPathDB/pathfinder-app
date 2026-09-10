Persistence
===========

Database layer: SQLAlchemy models, session management, and repositories
for users, experiments, streams, and control sets. Used by the HTTP layer
and background jobs.

Overview
--------

- **ORM Models** — User, ControlSet, and related models. Map to PostgreSQL tables.
- **Session** — Async engine and session factory, owned by the runtime package.
- **Repositories** — One repository per entity. Encapsulate queries and CRUD.

Design Decisions
~~~~~~~~~~~~~~~~

.. dropdown:: Async SQLAlchemy
   :icon: zap

   All database operations use ``async`` sessions with
   ``asyncpg`` (PostgreSQL's native async driver). This ensures the event loop
   is never blocked by database I/O, which matters for SSE streaming where many
   concurrent connections share the same process.

.. dropdown:: Repository pattern
   :icon: package

   Each domain entity (users, streams, control sets) has
   its own repository class that encapsulates queries. Services never construct
   raw SQL — they call repository methods. This makes testing easier (mock the
   repository, not the database) and keeps SQL details out of business logic.

.. dropdown:: Alembic for migrations
   :icon: versions

   Schema migrations use Alembic with async-compatible
   migration scripts. ``create_all`` is retained for development convenience
   (fresh databases), but production-like environments should use Alembic to
   apply schema changes incrementally.

.. dropdown:: UUID primary keys
   :icon: key

   All entities use UUID primary keys (via the custom
   ``GUID`` type decorator) for globally unique, non-sequential identifiers. This
   allows distributed ID generation without coordination and prevents information
   leakage from sequential IDs.

.. note::

   Schema migrations use **Alembic** (see ``alembic/versions/``).
   ``create_all`` is retained for development convenience on fresh databases.

ORM Models
----------

**Purpose:** SQLAlchemy models for users, control sets, experiments, streams,
gene sets, and operations. Define the schema and relationships.

**Key classes:** :py:class:`User`, :py:class:`ControlSet`, :py:class:`ExperimentRow`, :py:class:`Stream`

.. automodule:: pathfinder.persistence.models
   :members:
   :undoc-members:
   :show-inheritance:

Session Management
------------------

**Purpose:** The async database engine and the session factory every layer
uses. Owned by the ``assistant_core`` runtime package, which also owns the
declarative ``Base`` the application maps on.

.. automodule:: assistant_core.platform.db
   :members:
   :undoc-members:
   :show-inheritance:

Repositories
------------

**Purpose:** Data access layer. Encapsulates queries and CRUD operations.
Split into domain-specific repository modules.

.. automodule:: pathfinder.persistence.repositories.user
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.persistence.repositories.conversation
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.persistence.repositories.conversation_strategy
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.persistence.repositories.saved_strategy
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.persistence.repositories.control_set
   :members:
   :undoc-members:
   :show-inheritance:
