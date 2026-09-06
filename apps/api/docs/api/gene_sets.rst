Gene Sets
=========

Gene set management — persistent named collections of gene IDs with source
tracking, confidence scoring, ensemble analysis, and reverse search ranking.

Overview
--------

Gene sets are the bridge between strategy results and downstream analysis.
When a strategy step returns gene IDs, those IDs can be captured as a named
gene set for further use in enrichment analysis, cross-validation, and
workbench exploration.

.. mermaid::

   flowchart LR
       A["Strategy Results"] -->|capture| B["Gene Set"]
       C["User Paste/Upload"] -->|create| B
       D["Set Operations"] -->|derive| B
       B --> E["Enrichment"]
       B --> F["Confidence Scoring"]
       B --> G["Ensemble Analysis"]
       B --> H["Reverse Search"]
       B --> I["Export CSV/TXT"]

       style B fill:#7c3aed,color:#fff

**Key capabilities:**

- **CRUD** — Create gene sets from strategy results, user paste/upload, or
  derived operations (intersection, union, difference)
- **Confidence scoring** — Per-gene composite scores combining classification
  status, ensemble frequency, and enrichment support
- **Ensemble analysis** — Score genes by frequency across multiple gene sets
  (consensus voting)
- **Reverse search** — Rank gene set candidates by their recovery of known
  positive genes using pure set intersection (no WDK API calls needed)
- **Write-through persistence** — In-memory store backed by PostgreSQL for
  fast reads with durable writes

Design Decisions
~~~~~~~~~~~~~~~~

.. dropdown:: Why in-memory + DB?
   :class-title: sd-font-weight-bold

   Gene sets are read on nearly every workbench operation.
   The write-through store keeps a dict in memory for O(1) lookups while persisting
   mutations to PostgreSQL for durability. This avoids per-request DB round-trips
   for the common read path.

.. dropdown:: Why pure set operations for reverse search?
   :class-title: sd-font-weight-bold

   Gene IDs from strategy results are already materialized. Ranking candidates
   by set intersection (recall, precision, F1) is instantaneous compared to
   running WDK API calls. This makes the "which gene set best recovers my
   positive controls?" question answerable in milliseconds.

.. dropdown:: Source tracking
   :class-title: sd-font-weight-bold

   Each gene set records its source (``strategy``, ``paste``,
   ``upload``, ``derived``, ``saved``) for provenance. This lets the UI show where
   a gene set came from and whether it's "live" (from a strategy) or static.

Gene Set Store
--------------

**Purpose:** Write-through gene set store. In-memory dict for fast reads,
PostgreSQL persistence for durability. Thread-safe via asyncio.

.. automodule:: pathfinder.services.gene_sets.store
   :members:
   :undoc-members:
   :show-inheritance:

Gene Set Types
--------------

**Purpose:** Core data model for gene sets.

.. automodule:: pathfinder.services.gene_sets.types
   :members:
   :undoc-members:
   :show-inheritance:

Gene Set Operations
-------------------

**Purpose:** CRUD operations on gene sets — create, update, delete, list,
and derived set operations (intersection, union, difference).

.. automodule:: pathfinder.services.gene_sets.operations
   :members:
   :undoc-members:
   :show-inheritance:

Confidence Scoring
------------------

.. admonition:: Composite Confidence Score
   :class: tip

   .. math::

      C_g = w_1 \cdot \mathbb{1}[g \in TP] + w_2 \cdot \frac{f_g}{N} + w_3 \cdot E_g

   Where :math:`f_g` is the ensemble frequency (how many gene sets contain gene :math:`g`),
   :math:`N` is the total number of gene sets, and :math:`E_g` is the enrichment
   support score (membership in significant GO terms / pathways).

**Purpose:** Per-gene composite confidence scoring. Combines classification
status (TP/FP/FN/TN), ensemble frequency (how many gene sets include this gene),
and enrichment support (GO term / pathway membership) into a single score.

.. automodule:: pathfinder.services.gene_sets.confidence
   :members:
   :undoc-members:
   :show-inheritance:

Ensemble Analysis
-----------------

**Purpose:** Ensemble gene scoring by frequency across multiple gene sets.
Genes appearing in more sets get higher scores (consensus voting). Returns
sorted results for the workbench UI.

.. automodule:: pathfinder.services.gene_sets.ensemble
   :members:
   :undoc-members:
   :show-inheritance:

Reverse Search
--------------

**Purpose:** Rank gene set candidates by recovery of known positive genes.
Uses pure set intersection — no WDK API calls needed. Scores on recall,
precision, and F1 for given positive controls.

.. automodule:: pathfinder.services.gene_sets.reverse_search
   :members:
   :undoc-members:
   :show-inheritance:

VDI Publication
---------------

**Purpose:** Publish a gene set to the researcher's VEuPathDB workspace and read
the publication's status.

.. automodule:: pathfinder.services.gene_sets.vdi
   :members:
   :undoc-members:
   :show-inheritance:
