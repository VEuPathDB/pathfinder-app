Services
========

Core business logic for gene lookup, parameter optimization, control tests,
and catalog access. Services are stateless and orchestrated by the chat layer.

Overview
--------

- **Gene lookup** — Resolve gene names/symbols to VEuPathDB IDs via site-search
  or the WDK stateless reporter. Used when the user mentions genes from literature.
- **Parameter optimization** — Optimize search parameters against positive/negative
  control lists using Bayesian optimization (TPE), grid, or random search.
- **Control tests** — Run temporary WDK strategies with known gene lists and
  compute precision, recall, F1. Used by optimization and validation.
- **Catalog** — Get parameter specs, validate values, list sites/searches.
- **Strategy session** — Load and merge strategy state with conversation messages.

Gene Lookup
-----------

**Purpose:** Resolve gene names and IDs via VEuPathDB site-search and the WDK
stateless reporter. Used by the agent to validate gene references from
literature or user input.

**Key functions:**

- :py:func:`lookup_genes_by_text` — Search by free text (name, symbol, description)
- :py:func:`resolve_gene_ids` — Resolve a list of known IDs to full records via WDK

.. automodule:: pathfinder.services.gene_lookup
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.gene_lookup.lookup
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.gene_lookup.hydrate
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.gene_lookup.organism
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.gene_lookup.result
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.gene_lookup.scoring
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.gene_lookup.site_search
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.gene_lookup.wdk
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

Catalog (Parameter Validation)
-------------------------------

**Purpose:** Validation of search parameter values. Normalizes, canonicalizes,
and validates parameter values against WDK search specs before step creation
or strategy execution.

.. automodule:: pathfinder.services.catalog.param_validation
   :members:
   :undoc-members:
   :show-inheritance:

Export Service
--------------

**Purpose:** CSV/TSV/TXT generation and Redis temporary storage for data
exports. Generates downloadable files from strategy results, gene sets, and
enrichment results, storing them briefly in Redis for client retrieval.

.. automodule:: pathfinder.services.export.service
   :members:
   :undoc-members:
   :show-inheritance:

Control Tests
-------------

**Purpose:** Run positive/negative control gene lists against a WDK strategy
and compute precision, recall, F1, and related metrics. Used by parameter
optimization and for validation.

**Key function:** :py:func:`run_positive_negative_controls`

.. automodule:: pathfinder.services.control_tests
   :members:
   :undoc-members:
   :show-inheritance:

Control Helpers
---------------

**Purpose:** Formatting and parsing utilities for control test evaluation.
Encodes gene ID lists in various formats (newline, comma, JSON) and handles
temporary strategy cleanup.

.. automodule:: pathfinder.services.control_helpers
   :members:
   :undoc-members:
   :show-inheritance:

Tool Payloads
-------------

**Purpose:** The result shapes the MCP server and the agent toolsets both
render, so one catalog listing, one download URL and one control outcome
serve both adapters.

.. automodule:: pathfinder.services.tool_payloads
   :members:
   :undoc-members:
   :show-inheritance:

Search Reranking
----------------

**Purpose:** Reusable "fetch wide, rerank narrow" pattern for search results.
Robust fuzzy matching with exactness bonuses for gene ID lookups. Used to
improve relevance of WDK search results.

.. automodule:: pathfinder.services.search_rerank
   :members:
   :undoc-members:
   :show-inheritance:

Catalog (Parameters & Searches)
--------------------------------

**Purpose:** Retrieve and validate search parameters from VEuPathDB. Handles
parameter specs, dependent vocabularies, and search details. Used by tools
when the agent needs to discover or validate parameters.

**Key functions:**

- :py:func:`get_search_parameters` — Full parameter specs for a search
- :py:func:`validate_search_params` — Validate parameter values
- :py:func:`get_refreshed_dependent_params` — Refresh dependent parameter options

.. automodule:: pathfinder.services.catalog.parameters
   :members:
   :undoc-members:
   :show-inheritance:

Catalog (Sites & Record Types)
------------------------------

**Purpose:** Sites, record types, and search listing. Entry point for discovery.

.. automodule:: pathfinder.services.catalog.sites
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.catalog.searches
   :members:
   :undoc-members:
   :show-inheritance:

Catalog (Parameter Resolution)
-------------------------------

**Purpose:** WDK parameter fetching, caching, and vocabulary expansion.
Resolves search parameter specs with allowed values, handles dependent
vocabularies, and flattens nested parameter structures for agent consumption.

.. automodule:: pathfinder.services.catalog.param_resolution
   :members:
   :undoc-members:
   :show-inheritance:

Strategy Session
----------------

**Purpose:** Load and merge strategy state with conversation messages. Used
when switching strategies or restoring sessions.

.. automodule:: pathfinder.domain.strategy.session
   :members:
   :undoc-members:
   :show-inheritance:
   :no-index:

Experiment Seed Data
--------------------

**Purpose:** Generate demo experiments with pre-built multi-step strategies and
control sets across 13 VEuPathDB databases. Seeds use ``multi-step`` mode
internally to create strategy trees (the only place multi-step mode is used).
Triggered via ``POST /api/v1/experiments/seed`` or the Settings > Seeding UI.

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

