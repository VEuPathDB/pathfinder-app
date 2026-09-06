Evaluation Engine
=================

The **evaluation engine** is the backend service that powers the workbench's
analysis features. It evaluates search performance with positive/negative
control gene sets, computes classification and rank metrics, runs
cross-validation, and enrichment analysis. The workbench UI at ``/workbench``
consumes these endpoints.

.. mermaid::

   flowchart LR
       A["Gene Set + Controls"] --> G{targetGeneIds?}
       G -- yes --> H["Set Intersection<br/>(no WDK call)"]
       G -- no --> B["Run Search on WDK"]
       B --> C["Evaluate Controls"]
       H --> C
       C --> D["Metrics<br/>P/R/F1"]
       C --> E["Cross-Validation"]
       C --> F["Enrichment"]

       style A fill:#2563eb,color:#fff
       style G fill:#f59e0b,color:#000
       style H fill:#10b981,color:#fff
       style C fill:#7c3aed,color:#fff

Evaluation Modes
----------------

The evaluation engine supports two evaluation modes:

**Gene-ID mode** (workbench gene sets):
   When ``targetGeneIds`` is provided in the experiment config, the engine
   skips WDK search re-execution and evaluates using pure set intersection
   against the control genes. This is the correct path for workbench gene
   sets, which already contain materialized gene IDs.

**Search re-execution mode** (strategy evaluation):
   When ``targetGeneIds`` is absent, the engine runs the WDK search using
   ``searchName`` and ``parameters`` from the config and evaluates the
   results against controls. This is the correct path when evaluating a
   **search configuration itself** — e.g., when the AI agent builds a
   strategy and needs to test its performance before the results have been
   materialized into a gene set.

.. important::

   The **benchmark** and **evaluate** panels in the workbench both send
   ``targetGeneIds`` from the active gene set. This ensures metrics are
   computed against the actual gene set contents, not a potentially stale
   re-execution of search parameters.

Execution Endpoints
-------------------

.. list-table::
   :widths: 15 35 50
   :header-rows: 1

   * - Method
     - Endpoint
     - Description
   * - :bdg-success:`POST`
     - ``/api/v1/experiments/``
     - Create and run a single experiment (SSE)
   * - :bdg-success:`POST`
     - ``/api/v1/experiments/batch``
     - Run across multiple organisms (SSE)
   * - :bdg-success:`POST`
     - ``/api/v1/experiments/benchmark``
     - Run against multiple control sets (SSE)
   * - :bdg-success:`POST`
     - ``/api/v1/experiments/seed``
     - Seed demo strategies and control sets (SSE)

Analysis Endpoints
------------------

**Cross-experiment** (not scoped to a single experiment):

.. list-table::
   :widths: 15 35 50
   :header-rows: 1

   * - Method
     - Endpoint
     - Description
   * - :bdg-success:`POST`
     - ``/api/v1/experiments/overlap``
     - Pairwise gene set overlap (Jaccard, shared/unique genes)
   * - :bdg-success:`POST`
     - ``/api/v1/experiments/enrichment-compare``
     - Compare enrichment results across experiments

**Per-experiment** (scoped to ``{experiment_id}``):

.. list-table::
   :widths: 15 40 45
   :header-rows: 1

   * - Method
     - Endpoint
     - Description
   * - :bdg-success:`POST`
     - ``/api/v1/experiments/{id}/cross-validate``
     - Run cross-validation on an existing experiment
   * - :bdg-success:`POST`
     - ``/api/v1/experiments/{id}/enrich``
     - Run enrichment analysis
   * - :bdg-success:`POST`
     - ``/api/v1/experiments/{id}/re-evaluate``
     - Re-run evaluation (e.g. after changing controls)
   * - :bdg-success:`POST`
     - ``/api/v1/experiments/{id}/custom-enrich``
     - Custom enrichment request
   * - :bdg-success:`POST`
     - ``/api/v1/experiments/{id}/threshold-sweep``
     - Threshold sweep for a parameter
   * - :bdg-info:`GET`
     - ``/api/v1/experiments/{id}/export``
     - Download experiment report (HTML)

CRUD and Results
----------------

.. list-table::
   :widths: 15 40 45
   :header-rows: 1

   * - Method
     - Endpoint
     - Description
   * - :bdg-info:`GET`
     - ``/api/v1/experiments/``
     - List experiments (optional site filter)
   * - :bdg-info:`GET`
     - ``/api/v1/experiments/{id}``
     - Get one experiment
   * - :bdg-warning:`PATCH`
     - ``/api/v1/experiments/{id}``
     - Update (e.g. name)
   * - :bdg-danger:`DELETE`
     - ``/api/v1/experiments/{id}``
     - Delete an experiment

**Results browsing** (per-experiment):

.. list-table::
   :widths: 15 40 45
   :header-rows: 1

   * - Method
     - Endpoint
     - Description
   * - :bdg-info:`GET`
     - ``/api/v1/experiments/{id}/results/attributes``
     - List available result attributes
   * - :bdg-info:`GET`
     - ``/api/v1/experiments/{id}/results/records``
     - Paginated result records
   * - :bdg-success:`POST`
     - ``/api/v1/experiments/{id}/results/record``
     - Get single record detail
   * - :bdg-info:`GET`
     - ``/api/v1/experiments/{id}/results/distributions/{attr}``
     - Distribution data for an attribute
   * - :bdg-success:`POST`
     - ``/api/v1/experiments/{id}/refine``
     - Refine/filter result records

Persistence
-----------

Experiments are stored in the **experiments** table (see
:py:class:`pathfinder.persistence.models.ExperimentRow`): id, site_id,
name, status, data (full JSON), batch_id, benchmark_id, created_at, updated_at.
The experiment store (:py:mod:`pathfinder.services.experiment.store`)
keeps an in-memory cache and persists every mutation to PostgreSQL.

Control Sets
------------

Reusable positive/negative gene sets are managed at **/api/v1/control-sets**
(CRUD). They can be referenced when creating experiments (e.g.
control_set_id). See :py:class:`pathfinder.persistence.models.ControlSet`.

Experiment Streaming
--------------------

**Purpose:** Async generators that wrap an experiment run and yield typed
events. The single, batch and benchmark endpoints return these directly as
server-sent events.

.. automodule:: pathfinder.services.experiment.streaming
   :members:
   :undoc-members:
   :show-inheritance:

Service Layer
-------------

Core experiment service, orchestration, and store.

.. automodule:: pathfinder.services.experiment.service
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.experiment.store
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.experiment.helpers
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.experiment._deserialize
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.experiment.materialization
   :members:
   :undoc-members:
   :show-inheritance:

Classification
~~~~~~~~~~~~~~

**Purpose:** Gene record classification by experiment membership (TP/FP/FN/TN).
Adds ``_classification`` field to WDK records based on gene ID membership in
positive and negative control sets.

.. automodule:: pathfinder.services.experiment.classification
   :members:
   :undoc-members:
   :show-inheritance:

Evaluation Service
~~~~~~~~~~~~~~~~~~

**Purpose:** Re-evaluation and threshold sweep service. Pure business logic
for recomputing experiment metrics with updated controls or parameters.

Metrics and Evaluation
~~~~~~~~~~~~~~~~~~~~~~

.. admonition:: Key Metrics
   :class: tip

   .. math::

      \text{Precision} = \frac{|TP|}{|TP| + |FP|}
      \qquad
      \text{Recall} = \frac{|TP|}{|TP| + |FN|}
      \qquad
      F_1 = 2 \cdot \frac{\text{Precision} \cdot \text{Recall}}{\text{Precision} + \text{Recall}}

   Where :math:`TP` = true positives (returned genes in positive controls),
   :math:`FP` = false positives (returned genes in negative controls),
   :math:`FN` = false negatives (positive control genes not returned).

Classification metrics, rank metrics, and statistical utilities.

.. automodule:: pathfinder.services.experiment.metrics
   :members:
   :undoc-members:
   :show-inheritance:

Analysis Features
~~~~~~~~~~~~~~~~~

Cross-validation, overlap, comparison, robustness, and reporting.

.. automodule:: pathfinder.services.experiment.cross_validation
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.experiment.robustness
   :members:
   :undoc-members:
   :show-inheritance:

Step Analysis
~~~~~~~~~~~~~

Multi-step strategy analysis: per-step evaluation, operator comparison,
contribution analysis, and parameter sensitivity.

Types
~~~~~

Pydantic models for experiment configuration, metrics, enrichment, and results.

.. automodule:: pathfinder.services.experiment.types
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.experiment.types.experiment
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.experiment.types.core
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.experiment.types.metrics
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.experiment.types.serialization
   :members:
   :undoc-members:
   :show-inheritance:

Enrichment
----------

**Purpose:** The custom gene-set variant and the statistics enrichment results
share. Running an analysis by value is the ``veupathdb-mcp``
distribution's ``veupathdb_mcp.wdk.enrichment``.

.. automodule:: pathfinder.services.enrichment.custom
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.services.enrichment.stats
   :members:
   :undoc-members:
   :show-inheritance:

Seed Data
~~~~~~~~~

Generate demo experiments with curated multi-step strategies and control sets
across 13 VEuPathDB databases. This is the only place the backend's
``multi-step`` mode is used. See :doc:`services` for full seed module reference.
