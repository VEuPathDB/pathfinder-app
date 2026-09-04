AI Tools
========

Every tool the agents can call. A tool is a plain async function registered on
a pydantic-ai ``FunctionToolset``; the toolset a phase gets decides what that
phase is allowed to do. Tools are thin: they call services, never integrations
or persistence directly.

Overview
--------

- **Toolsets** — One ``FunctionToolset`` per phase. FRAME, BUILD, VERIFY and
  EDA each see a different set.
- **Standalone tools** — The tool functions themselves, grouped by subject.
- **Durable tools** — Long-running tools that defer their work to the worker
  and answer on a later turn.

.. important::

   A phase can only call what its toolset carries. Widening a phase means
   editing its toolset module, not adding a decorator to a function.

Toolsets
--------

**Purpose:** Build the phase-scoped toolsets. Each module assembles the tools
one pipeline phase may call, and ``_dynamic`` narrows a tool's schema for the
run it is about to make.

.. automodule:: pathfinder.ai.tools.toolsets.frame
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.toolsets.execution
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.toolsets.verification
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.toolsets.eda
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.toolsets._dynamic
   :members:
   :undoc-members:
   :show-inheritance:

Durable Tools
-------------

**Purpose:** A durable tool is a deferred tool. At call time it writes a
``background_tasks`` row, defers a Procrastinate job, emits
``data-background-task-started`` and raises ``CallDeferred``. The worker runs
the real implementation and opens a new turn carrying the result.

.. automodule:: pathfinder.ai.tools.durable
   :members:
   :undoc-members:
   :show-inheritance:

Catalog Discovery
-----------------

**Purpose:** Find what a site offers: record types, searches, categories, and
the parameters and vocabularies a search takes. Every answer is read live from
WDK through the catalog service.

.. automodule:: pathfinder.ai.tools.standalone.catalog
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.catalog_discovery
   :members:
   :undoc-members:
   :show-inheritance:

FRAME Tools
-----------

**Purpose:** Turn the request into an operational spec: state the criteria,
bind each one to a search with resolved parameters, fold them into a tree, and
reuse a strategy the user already saved.

.. automodule:: pathfinder.ai.tools.standalone.frame_spec
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.frame_structure
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.saved_strategies
   :members:
   :undoc-members:
   :show-inheritance:

Strategy Tools
--------------

**Purpose:** Build the strategy declaratively, edit an existing one step by
step, inspect the graph, and attach a filter, analysis or report to a step.

.. automodule:: pathfinder.ai.tools.standalone.strategy
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.strategy_edits
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.strategy_graph
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.strategy_attach
   :members:
   :undoc-members:
   :show-inheritance:

Execution and Results
---------------------

**Purpose:** Read what a built step returns: counts, sample records, download
URLs, and single-gene detail.

.. automodule:: pathfinder.ai.tools.standalone.execution
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.results
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.gene
   :members:
   :undoc-members:
   :show-inheritance:

Verification Tools
------------------

**Purpose:** Test a strategy. Control tests against positive and negative
gene sets, parameter optimization, variant comparison, and scored comparison
against a saved control set.

.. automodule:: pathfinder.ai.tools.standalone.experiment
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.control_sets
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.optimization
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.variant_comparison
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.scored_comparison
   :members:
   :undoc-members:
   :show-inheritance:

EDA Tools
---------

**Purpose:** Explore a study in conversation: find it, read its shape, open an
analysis, subset it, run the durable differential-expression compute, and
export the result into the strategy as a WDK step.

.. automodule:: pathfinder.ai.tools.standalone.eda_catalog
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.eda_analysis
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.eda_compute
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.eda_step
   :members:
   :undoc-members:
   :show-inheritance:

Gene Sets and Export
--------------------

**Purpose:** Read and write workbench gene sets, and export a strategy, a gene
set or an experiment result.

.. automodule:: pathfinder.ai.tools.standalone.workbench
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.workbench_read
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.export
   :members:
   :undoc-members:
   :show-inheritance:

Research Tools
--------------

**Purpose:** Web search and literature search, shared by every phase that may
need outside evidence.

.. automodule:: pathfinder.ai.tools.standalone.research
   :members:
   :undoc-members:
   :show-inheritance:

Conversation and Memory
-----------------------

**Purpose:** Save and load a strategy on the thread, search cross-thread
memory, and write a memory the user asked to keep.

.. automodule:: pathfinder.ai.tools.standalone.conversation
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.memory_tools
   :members:
   :undoc-members:
   :show-inheritance:

Reasoning and Escape
--------------------

**Purpose:** An explicit reasoning scratchpad between tool calls, and the exit
ramp a phase takes when its toolset cannot express what the turn needs.

.. automodule:: pathfinder.ai.tools.standalone.think
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.tools.standalone.escape_hatch
   :members:
   :undoc-members:
   :show-inheritance:

