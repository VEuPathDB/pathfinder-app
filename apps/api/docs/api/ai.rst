AI & Models
===========

Per-provider settings, pricing, and prompt loading. This is
what decides which LLM each phase runs on and what a run costs; the model
catalog and the tier presets that back it are in :doc:`platform`.

Overview
--------

- **Model Resolution** — Pick the catalog entry a run uses from the request
  override, the persisted conversation state, or the role default.
- **Model Settings** — Per-provider ``ModelSettings`` for pydantic-ai.
- **Pricing** — Cost per run from token usage.
- **Prompts** — The prompt files and the loader that reads them.

.. note::

   Each phase role carries its own default model
   (:py:func:`strategist.ai.agents.registry.phase_defaults`). A request may
   override the model per phase; the conversation remembers the last choice.

Model Resolution
----------------

**Purpose:** Resolve the catalog entry a run uses from the per-request
override, the persisted conversation state, or the role default.

.. automodule:: strategist.ai.agents._model_resolution
   :members:
   :undoc-members:
   :show-inheritance:

Prompts
-------

**Purpose:** Read the prompt files that the Lead and the phase sub-agents
share. The text lives in markdown beside the loader.

.. automodule:: strategist.ai.prompts.loader
   :members:
   :undoc-members:
   :show-inheritance:
