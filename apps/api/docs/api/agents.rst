Agents
======

PathFinder runs one Lead agent and three phase sub-agents, all built with
`pydantic-ai <https://ai.pydantic.dev/>`_. The Lead is the only voice the user
hears. It calls each phase as a tool and reads a typed ledger between calls,
so a phase is a tool invocation rather than a node in a fixed graph.

.. list-table:: Agent Comparison
   :widths: 20 30 25 25
   :header-rows: 1

   * - Agent
     - Purpose
     - Toolset
     - When Used
   * - **Lead**
     - The user-facing voice; routes the turn
     - Sub-agent tools, ledger reads, memory, consult
     - Every chat turn
   * - **FRAME**
     - Turn the request into an operational spec
     - Retrieval, operationalize, bind, resolve
     - Called by the Lead when the spec is missing or stale
   * - **BUILD**
     - Build and edit the strategy declaratively
     - Declarative build plus atomic edits
     - Called by the Lead once a spec exists
   * - **VERIFY**
     - Test, analyse and export the result
     - Control tests, optimization, export, the evidence card
     - Called by the Lead after a build

Lead Agent
----------

**Purpose:** Own the conversation. The Lead classifies the user's intent,
invokes the phase sub-agents as tools, reads the typed
:py:class:`~pathfinder.ai.lead.ledger.InvestigationLedger` after each call,
and asks the user a blocking question through ``consult_user``. It never
writes to WDK itself.

**Key functions:** :py:func:`build_lead_agent`, :py:func:`classify_user_intent`,
:py:func:`consult_user`, :py:func:`read_ledger_section`

.. automodule:: pathfinder.ai.lead.lead_agent
   :members:
   :undoc-members:
   :show-inheritance:

Investigation Ledger
--------------------

**Purpose:** The typed record of what the turn has established: the spec, the
searches chosen, the counts observed, and the verification digest. The Lead
reads it instead of re-reading sub-agent transcripts.

.. automodule:: pathfinder.ai.lead.ledger
   :members:
   :undoc-members:
   :show-inheritance:

Sub-agent Dispatch
------------------

**Purpose:** Run one phase sub-agent on behalf of the Lead: build its message
list, stream its events into the turn, and fold its result into the ledger.

.. automodule:: pathfinder.ai.lead.sub_agent_tools
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.lead.sub_agent_dispatch
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.lead.sub_agent_stream
   :members:
   :undoc-members:
   :show-inheritance:

FRAME Agent
-----------

**Purpose:** Turn the user's request into an operational spec: the record
type, the criteria, and the search plus bound parameters each criterion
resolves to. FRAME proposes; it does not push to WDK.

**Key function:** :py:func:`build_frame_agent`

.. automodule:: pathfinder.ai.agents.frame
   :members:
   :undoc-members:
   :show-inheritance:

BUILD Agent
-----------

**Purpose:** Build the strategy from the operational spec and apply atomic
edits to an existing one. This is the only agent that mutates the strategy
graph.

**Key function:** :py:func:`build_execution_agent`

.. automodule:: pathfinder.ai.agents.execution
   :members:
   :undoc-members:
   :show-inheritance:

VERIFY Agent
------------

**Purpose:** Test the built strategy: control tests, parameter optimization,
variant comparison, and export. Its digest is what the Lead reads to decide
whether the turn succeeded, and every finished check leaves an evidence card
(:py:mod:`pathfinder.domain.evidence`) read from its control tests and the site.

**Key function:** :py:func:`build_verification_agent`

.. automodule:: pathfinder.ai.agents.verification
   :members:
   :undoc-members:
   :show-inheritance:

Phase Roles and Model Defaults
------------------------------

**Purpose:** The four phase roles and the model each one runs on when the user
pins nothing. Every agent is built per run, so a default is the model its
factory bakes in.

.. automodule:: pathfinder.ai.agents.roles
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.agents.registry
   :members:
   :undoc-members:
   :show-inheritance:

Shared Agent State
------------------

**Purpose:** The state a sub-agent carries across its own tool calls, and the
history processor that keeps a long phase inside its context budget.

.. automodule:: pathfinder.ai.agents.state
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: pathfinder.ai.agents.compactor
   :members:
   :undoc-members:
   :show-inheritance:
