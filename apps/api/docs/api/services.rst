Services
========

Core business logic for parameter optimization, export and seeding. Services
are stateless and orchestrated by the chat layer.

Overview
--------

- **Parameter optimization** — Optimize search parameters against positive/negative
  control lists using Bayesian optimization (TPE), grid, or random search.
- **Export** — Generate a downloadable file from strategy results and gene sets.
- **Experiment seeds** — Demo experiments with pre-built strategies and controls.
- **Evidence facade** — The one door the agent and the jobs use to reach gene
  sets, control sets, variant comparisons and parameter sweeps.

The catalog, gene lookup, control tests and tool payloads are the
``veupathdb-mcp`` distribution, imported as ``veupathdb_mcp``; its
README is the reference for them.

Evidence Facade
---------------

**Purpose:** ``pathfinder.ai`` and ``pathfinder.jobs`` reach the evidence
producers only through this package. Every name here is a function with a body;
a result type is imported from the module that defines it. The import-linter
contract "The agent and the jobs reach the evidence producers only through its
facade" names the modules the facade owns.

.. automodule:: pathfinder.services.evidence.gene_sets
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.evidence.control_sets
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.evidence.comparisons
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.evidence.optimization
   :members:
   :undoc-members:
   :show-inheritance:

Parameter Optimization
----------------------

**Purpose:** Optimize search parameters against positive/negative control gene
lists using Bayesian optimization (TPE), grid search, or random search. Each
trial runs a temporary WDK strategy and scores the result.

**Key types:** ``ParameterSpec``, ``OptimizationConfig``, ``OptimizationResult``

.. automodule:: pathfinder.services.parameter_optimization
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.parameter_optimization.config
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.parameter_optimization.scoring
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.parameter_optimization.builders
   :members:
   :undoc-members:
   :show-inheritance:

Export Service
--------------

**Purpose:** CSV/TSV/TXT/JSON generation for data exports. Generates
downloadable files from strategy results and gene sets, and stores them briefly
in Postgres for client retrieval.

.. automodule:: pathfinder.services.export.service
   :members:
   :undoc-members:
   :show-inheritance:

Experiment Seed Data
--------------------

**Purpose:** Generate demo strategies with pre-built multi-step trees and
control sets across 13 VEuPathDB databases. Triggered via ``POST /api/v1/seed``
or the Settings > Seeding UI.

Each database has curated seed definitions with organism-specific searches,
known positive/negative gene controls, and step trees that demonstrate
real research workflows (e.g. drug resistance genes in PlasmoDB, virulence
factors in TriTrypDB).

.. automodule:: pathfinder.services.experiment.seed
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.experiment.seed.runner
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.experiment.seed.types
   :members:
   :undoc-members:
   :show-inheritance:

