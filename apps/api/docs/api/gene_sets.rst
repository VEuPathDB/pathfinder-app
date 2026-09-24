Gene Sets
=========

Gene set management - persistent named collections of gene IDs with source
tracking, export, import and publication to VEuPathDB.

Overview
--------

Gene sets are the bridge between strategy results and downstream analysis.
When a strategy step returns gene IDs, those IDs can be captured as a named
gene set for control tests, export and publication.

.. mermaid::

   flowchart LR
       A["Strategy Results"] -->|capture| B["Gene Set"]
       C["Pasted IDs"] -->|import| B
       B --> I["Export CSV/TXT"]
       B --> V["Publish to VDI"]

       style B fill:#7c3aed,color:#fff

**Key capabilities:**

- **Capture and import** - A build saves the root step's genes; the ``/import``
  slash command saves a pasted list
- **Write-through persistence** - In-memory store backed by PostgreSQL for
  fast reads with durable writes

Design Decisions
~~~~~~~~~~~~~~~~

.. dropdown:: Why in-memory + DB?
   :class-title: sd-font-weight-bold

   The agent reads gene sets during a turn. The write-through store keeps a
   dict in memory for O(1) lookups while persisting mutations to PostgreSQL
   for durability.

.. dropdown:: Source tracking
   :class-title: sd-font-weight-bold

   Each gene set records its source (``strategy``, ``paste``,
   ``upload``, ``derived``, ``saved``) for provenance. This shows where a
   gene set came from and whether it's "live" (from a strategy) or static.

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

**Purpose:** Create, re-sync, rename, list and delete gene sets.

.. automodule:: pathfinder.services.gene_sets.operations
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
