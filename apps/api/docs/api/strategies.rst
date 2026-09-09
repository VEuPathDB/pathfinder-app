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

.. automodule:: pathfinder.services.strategies.plan_validation
   :members:
   :undoc-members:
   :show-inheritance:

WDK Conversion
--------------

**Purpose:** Pure WDK → AST conversion. Parses WDK strategy payloads into
internal ``StrategyAST``, extracts field values, and normalizes parameters.

.. admonition:: WDK Wire Format and Parameter Coercion
   :class: note

   WDK stores multi-pick parameter values as **JSON-encoded strings** (e.g.
   ``'["Plasmodium falciparum 3D7"]'`` rather than a native array). The wire
   format is preserved in the stored plan when a strategy is synced from WDK.

   The frontend step editor automatically coerces these JSON strings into
   native arrays when parameter specs load, so widgets (TreeBox, Select,
   etc.) can match values against their vocabulary options. This coercion
   runs once per editor mount via ``coerceParametersForSpecs`` in the
   ``useStepParameters`` hook.

.. automodule:: pathfinder.services.strategies.wdk_conversion
   :members:
   :undoc-members:
   :show-inheritance:

WDK Sync
--------

**Purpose:** Fetch WDK strategies and sync into CQRS projections.
Lazy detail fetching, isSaved sync, and projection upsert.

.. automodule:: pathfinder.services.strategies.wdk_sync
   :members:
   :undoc-members:
   :show-inheritance:

WDK Step Counts
---------------

**Purpose:** Per-step result count computation. Uses anonymous reports
for leaf-only strategies (fast) and temporary WDK compilation for complex
strategies. Results are cached by plan hash.

.. automodule:: pathfinder.services.strategies.wdk_counts
   :members:
   :undoc-members:
   :show-inheritance:

Strategy Build
--------------

**Purpose:** High-level strategy build orchestration. Coordinates step
creation and graph assembly.

.. automodule:: pathfinder.services.strategies.build
   :members:
   :undoc-members:
   :show-inheritance:

Step Push
---------

**Purpose:** Plan the WDK calls one step needs, then make them. A failed push
leaves the step in the local graph for the sync service to retry.

.. automodule:: pathfinder.services.strategies.step_push_planner
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.strategies.step_wdk_push
   :members:
   :undoc-members:
   :show-inheritance:

Auto Import
-----------

**Purpose:** Automatic import of WDK strategies into PathFinder.

.. automodule:: pathfinder.services.strategies.auto_import
   :members:
   :undoc-members:
   :show-inheritance:

Sync and Reconcile
------------------

**Purpose:** Push local graph state to WDK — step tree, strategy, counts,
decorations — and read live WDK state back to self-heal ``sync_state`` after
a partial push.

.. automodule:: pathfinder.services.strategies.sync
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.strategies.sync_state
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.strategies.reconcile
   :members:
   :undoc-members:
   :show-inheritance:

Session Factory
---------------

**Purpose:** Create and restore strategy sessions. Loads strategy state
from the database for chat context.

.. automodule:: pathfinder.services.strategies.session_factory
   :members:
   :undoc-members:
   :show-inheritance:

Declarative Build
-----------------

**Purpose:** Build a strategy from a declarative step tree: diff it against
the tree already stored, persist the new AST to the conversation row, push
the steps, and sync.

.. automodule:: pathfinder.services.strategies.spec_build
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.strategies.commit
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.strategies.persist
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.strategies.materialize
   :members:
   :undoc-members:
   :show-inheritance:
