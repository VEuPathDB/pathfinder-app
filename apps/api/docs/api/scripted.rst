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

