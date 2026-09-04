AI & Models
===========

Model catalog, per-provider settings, tier presets, pricing, and prompt
loading. This is what decides which LLM each phase runs on and what a run
costs.

Overview
--------

- **Model Catalog** — Model metadata, provider mappings, reasoning-effort
  config. Populates the model picker; enforces sampling constraints.
- **Model Resolution** — Pick the catalog entry a run uses from the request
  override, the persisted conversation state, or the role default.
- **Model Settings** — Per-provider ``ModelSettings`` for pydantic-ai.
- **Tier Presets** — Map a provider and a tier to a model per phase.
- **Pricing** — Cost per run from token usage.
- **Prompts** — The prompt files and the loader that reads them.

.. note::

   Each phase role carries its own default model
   (:py:func:`pathfinder.ai.agents.registry.phase_defaults`). A request may
   override the model per phase; the conversation remembers the last choice.

Model Catalog
-------------

**Purpose:** The catalog of selectable models: cloud entries plus local
entries read from YAML. Records which models support reasoning and which
sampling parameters they refuse.

**Key functions:** :py:func:`get_model_entry`, :py:func:`get_model_catalog`

.. automodule:: pathfinder.ai.models.catalog
   :members:
   :undoc-members:
   :show-inheritance:

Model Resolution
----------------

**Purpose:** Resolve the catalog entry a run uses from the per-request
override, the persisted conversation state, or the role default.

.. automodule:: pathfinder.ai.agents._model_resolution
   :members:
   :undoc-members:
   :show-inheritance:

Model Settings
--------------

**Purpose:** Per-provider model settings for pydantic-ai. The stable
``provider:model`` id is what pydantic-ai infers the provider from.

.. automodule:: pathfinder.ai.models.settings
   :members:
   :undoc-members:
   :show-inheritance:

Tier Presets
------------

**Purpose:** Map a ``(provider, tier)`` pair to a model and reasoning effort
for each pipeline phase. The frontend fetches these to populate the picker.

.. automodule:: pathfinder.ai.models.tiers
   :members:
   :undoc-members:
   :show-inheritance:

Scripted Model
--------------

**Purpose:** PathFinder's script for the deterministic test model. The Lead
routes on the latest user message and drives a scripted FRAME, BUILD and
VERIFY flow, so an end-to-end run costs nothing and repeats exactly.

**Design:** Only the LLM call is scripted. WDK, PostgreSQL and the worker all
run for real, which is what makes the mock useful for integration coverage.

.. automodule:: pathfinder.ai.models.mock
   :members:
   :undoc-members:
   :show-inheritance:

Model Pricing
-------------

**Purpose:** Cost per run in USD, looked up from the live price snapshot.

.. automodule:: pathfinder.ai.pricing
   :members:
   :undoc-members:
   :show-inheritance:

Prompts
-------

**Purpose:** Read the prompt files that the Lead and the phase sub-agents
share. The text lives in markdown beside the loader.

.. automodule:: pathfinder.ai.prompts.loader
   :members:
   :undoc-members:
   :show-inheritance:
