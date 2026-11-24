Strategy Services
=================

Plan normalization, validation, serialization, and WDK snapshot handling.
Bridges between the domain AST and the persistence/WDK layer.

Overview
--------

- **Plan Normalization** — Coerce parameter values, fill defaults, resolve
  vocab terms for WDK compatibility. Called before save or push.
- **Plan Validation** — Validate against WDK constraints; structured errors.
- **Serialization** — Convert between domain AST and persistence format.
- **WDK Snapshot** — Build WDK-compatible step trees from the domain plan.

Plan Normalization
------------------

**Purpose:** Normalize plans for WDK compatibility. Coerce parameter values
to the expected types, fill defaults, resolve vocabulary terms. Called before
save or push to VEuPathDB.

**Key function:** :py:func:`canonicalize_plan_parameters`

Plan Validation
---------------

**Purpose:** Validate plans against WDK constraints. Required parameters, valid
search names, step structure. Returns structured validation errors with field paths.

**Key function:** :py:func:`validate_plan_or_raise`

.. automodule:: strategist.services.strategies.plan_validation
   :members:
   :undoc-members:
   :show-inheritance:

WDK Sync
--------

**Purpose:** Fetch WDK strategies and sync into CQRS projections.
Lazy detail fetching, isSaved sync, and projection upsert.

.. automodule:: strategist.services.strategies.wdk_sync
   :members:
   :undoc-members:
   :show-inheritance:

WDK Step Counts
---------------

**Purpose:** Per-step result count computation. Uses anonymous reports
for leaf-only strategies (fast) and temporary WDK compilation for complex
strategies. Results are cached by plan hash.

.. automodule:: strategist.services.strategies.wdk_counts
   :members:
   :undoc-members:
   :show-inheritance:

Commit
------

**Purpose:** The one path that writes steps and a strategy to WDK: refuse a
tree the site cannot run, plan the calls each step needs against what WDK
holds, validate once, push, put the tree and read back what WDK holds. A saved
or internal strategy is kept whole or deleted.

.. automodule:: strategist.services.strategies.commit_tree
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: strategist.services.strategies.step_push_planner
   :members:
   :undoc-members:
   :show-inheritance:

Auto Import
-----------

**Purpose:** Automatic import of WDK strategies into Strategist.

.. automodule:: strategist.services.strategies.auto_import
   :members:
   :undoc-members:
   :show-inheritance:

Sync and Reconcile
------------------

**Purpose:** The step tree as WDK keys it, the strategy's labels, and live WDK
state read back to self-heal ``sync_state`` after a partial push.

.. automodule:: strategist.services.strategies.sync
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: strategist.services.strategies.site_counts
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: strategist.services.strategies.sync_state
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: strategist.services.strategies.reconcile
   :members:
   :undoc-members:
   :show-inheritance:

Session Factory
---------------

**Purpose:** Create and restore strategy sessions. Loads strategy state
from the database for chat context.

.. automodule:: strategist.services.strategies.session_factory
   :members:
   :undoc-members:
   :show-inheritance:

Declarative Build
-----------------

**Purpose:** Build a strategy from a declarative step tree: diff it against
the tree already stored, persist the new AST to the conversation row, push
the steps, and sync.

.. automodule:: strategist.services.strategies.spec_build
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: strategist.services.strategies.commit
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: strategist.services.strategies.persist
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: strategist.services.strategies.materialize
   :members:
   :undoc-members:
   :show-inheritance:
