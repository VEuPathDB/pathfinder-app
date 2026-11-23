Scripted Model
==============

**Where it lives:** ``strategist_scripted``, beside ``strategist`` under
``apps/api/src``. Only the test environment and the e2e image stage contain
it; production reaches it through ``strategist.ai.scripted``.

**Purpose:** Strategist's script for the deterministic test model. The Lead
routes on the latest user message and drives a scripted FRAME, BUILD and
VERIFY flow, so an end-to-end run costs nothing and repeats exactly.

**Design:** Only the LLM call is scripted. WDK, PostgreSQL and the worker all
run for real, which is what makes the mock useful for integration coverage.

.. automodule:: strategist_scripted.models
   :members:
   :undoc-members:
   :show-inheritance:

Seed Catalog
------------

**Purpose:** Curated strategies with multi-step trees and control sets across
the VEuPathDB databases, read by the deterministic mock model, the measurement
refresher and the live tests.

Each database has curated seed definitions with organism-specific searches,
known positive/negative gene controls, and step trees that demonstrate
real research workflows (e.g. drug resistance genes in PlasmoDB, virulence
factors in TriTrypDB).

.. automodule:: strategist_scripted.seeds.catalog
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: strategist_scripted.seeds.types
   :members:
   :undoc-members:
   :show-inheritance:

Dev Routes
----------

**Purpose:** The routes only a mock deployment mounts: the dev login the
Playwright suite signs in with, and the stored sample audit run. They are never
written into the OpenAPI spec.

.. automodule:: strategist_scripted.dev_routes
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: strategist_scripted.audit.sample_run
   :members:
   :undoc-members:
   :show-inheritance:
