Evaluation Engine
=================

The **evaluation engine** scores one search against positive and negative
control genes. ``compare_variants_scored`` runs one experiment per search
variant (:py:mod:`pathfinder.services.experiment.scored_comparison`), and the
control tests VERIFY runs read the same metrics. No HTTP route runs an
experiment.

.. mermaid::

   flowchart LR
       A["Search + Controls"] --> B["Run Search on WDK"]
       B --> C["Evaluate Controls"]
       C --> D["Metrics<br/>P/R/F1"]

       style A fill:#2563eb,color:#fff
       style C fill:#7c3aed,color:#fff

Seed Endpoint
-------------

.. list-table::
   :widths: 15 35 50
   :header-rows: 1

   * - Method
     - Endpoint
     - Description
   * - :bdg-success:`POST`
     - ``/api/v1/seed``
     - Seed demo strategies and control sets (SSE)

Persistence
-----------

Experiments are stored in the **experiments** table (see
:py:class:`pathfinder.persistence.models.ExperimentRow`): id, site_id,
name, status, data (full JSON), created_at, updated_at.
The experiment store (:py:mod:`pathfinder.services.experiment.store`)
keeps an in-memory cache and persists every mutation to PostgreSQL.

Control Sets
------------

Reusable positive/negative gene sets are written and read by the agent's
control-set tools, through :py:mod:`pathfinder.services.evidence.control_sets`.
See :py:class:`pathfinder.persistence.models.ControlSet`.

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

.. automodule:: pathfinder.services.experiment.materialization
   :members:
   :undoc-members:
   :show-inheritance:

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

Classification metrics and statistical utilities.

.. automodule:: pathfinder.services.experiment.metrics
   :members:
   :undoc-members:
   :show-inheritance:

Types
~~~~~

Pydantic models for experiment configuration, metrics and results.

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

Control enrichment
------------------

**Purpose:** The hypergeometric row a control result carries, read with the
tool server's statistic. GO, pathway and word enrichment are analyses the site
runs on a step.

.. automodule:: pathfinder.services.evidence.control_enrichment
   :members:
   :undoc-members:
   :show-inheritance:

Separation
----------

**Purpose:** A separation run's result as the report PathFinder shows and the
offer it builds: the measured tree as a spec, each criterion's counts, and what
each criterion adds.

.. automodule:: pathfinder.services.separation.offer
   :members:
   :undoc-members:
   :show-inheritance:

Seed Data
~~~~~~~~~

Generate demo strategies with curated multi-step trees and control sets across
13 VEuPathDB databases. See :doc:`services` for full seed module reference.
