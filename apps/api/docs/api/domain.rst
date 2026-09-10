Domain Logic
============

Pure domain logic with no I/O or framework dependencies. The strategy authoring
model, the parameter model and the WDK value types ship in the
``veupathdb-py`` distribution; what remains here is PathFinder's own reading of them.

Overview
--------

- **Strategy Validation** — Validate against WDK constraints; emit field paths.
- **Strategy Explanation** — Prose for a plan the researcher is about to run.

Strategy Validation
-------------------

**Purpose:** Validate plans against WDK constraints: required parameters, valid
search names, step structure. Emits ``ValidationError`` with field paths for
UI display.

**Key function:** :py:func:`validate_strategy`

.. automodule:: pathfinder.domain.strategy.validate
   :members:
   :undoc-members:
   :show-inheritance:

Strategy - Additional Modules
-----------------------------

.. automodule:: pathfinder.domain.strategy.explain
   :members:
   :undoc-members:
   :show-inheritance:
