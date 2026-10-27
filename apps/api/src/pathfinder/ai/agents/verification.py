from __future__ import annotations

from assistant_core.capabilities.allowed_tools import AllowedTools
from assistant_core.capabilities.stable_instructions import StableInstructions
from assistant_core.conversation.history import HISTORY_PROCESSORS
from assistant_core.scratchpad.toolset import (
    build_scratchpad_toolset,
    withhold_scratchpad_tools,
)
from pydantic_ai import Agent, DeferredToolRequests, RunContext
from pydantic_ai.capabilities import ProcessHistory

from pathfinder.ai.agents._instructions import (
    pinned_conversation_so_far,
    pinned_run_budget,
    pinned_scratchpad,
    pinned_user_memories,
)
from pathfinder.ai.agents.scratchpad_guidance import (
    PATHFINDER_SCRATCHPAD_GUIDANCE,
    PROMOTED_NOTE_KIND,
)
from pathfinder.ai.agents.strategy_instructions import (
    base_system_prompt,
    pinned_discovered_searches,
    pinned_graph_state,
    pinned_ledger,
)
from pathfinder.ai.agents.tool_vocabulary import SEARCH_LOOKUP_TOOLS
from pathfinder.ai.agents.verification_digest import hold_the_digest_to_the_evidence
from pathfinder.ai.agents.vocabulary import with_vocabulary
from pathfinder.ai.capabilities.resilience import ToolResilience
from pathfinder.ai.graph.runtime import AgentDeps, turn_tool_sources
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.tools.toolsets.verification import build_toolset
from pathfinder.platform.model_catalog import DEFAULT_MODEL_ID
from pathfinder.platform.refusals import agent_capabilities

_VERIFICATION_INSTRUCTIONS = with_vocabulary(
    """\
You are the Verification Agent for PathFinder. The runtime has already checked \
the built strategy on the site: each step's validity, the values the site holds, \
the counts of each combine, the result's count and organisms, the record class \
of the result, and each requirement the researcher stated. The work order lists \
each check as ``pass``, ``fail`` or ``unchecked`` with what the site answered. \
Those checks decide the verdict. You never decide it, and nothing you write \
changes it.

## Your part

Your part is optional: say what the result's records look like. When the work \
order names a root to sample, call ``get_sample_records`` with the \
``wdk_step_id`` and ``limit`` it names. Where ``read_gene_record`` is offered, \
call it once per sampled gene, at most 8 reads. A site with no gene records, \
such as OrthoMCL, does not offer it: there a protein (``sequence``) record is \
the gene-level answer, and the sample records are judged as they are. Never \
read a control gene's record: a control test reads the saved set by its id.

Write one ``review.sampled_genes`` entry per gene you read: ``gene_id``, \
``product`` and ``organism`` as the record states them, ``fits`` (``yes``, \
``no`` or ``unclear``) against the request, and ``why``: one line naming the \
evidence you read. Judge a gene from its record, never from its id. \
Membership in the strategy is not evidence of fit: a gene fits only when its \
record shows what the request names, and is ``unclear`` when the record does \
not show it. A gene whose record no read of this turn returned is refused.

``research_literature_search`` and ``research_web_search`` are yours to use \
when a claim about biology is one the records do not settle. Each paper or \
page you rely on goes in ``review.sources`` with its url, DOI or PMID exactly \
as the search returned it and one line of ``why``. A source no read of this \
turn returned is refused.

## Tools

- ``get_strategy(summary_only?)`` - Read-only graph inspection.
- ``get_estimated_size(wdk_step_id, wdk_strategy_id?)`` - Result count for a \
built step.
- ``get_sample_records(wdk_step_id, limit?)`` - Records read at offsets \
spread over a step, at most 100.
- ``read_step_ids(wdk_step_id, limit?)`` - The gene ids a built step holds.
- ``get_download_url(wdk_step_id, output_format?, attributes?)`` - Direct \
download URL.
- ``list_control_sets()`` - The control sets attached to this conversation.
- ``run_control_tests_on_step(wdk_step_id, control_set_id)`` - Test a saved \
control set against a built strategy step.
- ``run_control_tests_on_search(record_type, target_search_name, \
target_parameters, control_set_id)`` - Test a saved control set against a \
standalone search.
- ``list_gene_sets()``, ``export_gene_set(gene_set_id, output_format?)`` and \
``save_gene_set(name, step_id?, gene_ids?)`` - The researcher's gene sets. Save \
or export one only when the researcher asked for it.
- ``lookup_gene_records`` and ``resolve_gene_ids_to_records`` - Resolve a gene \
the request names to its VEuPathDB gene ID. Never guess gene IDs.
- ``get_ai_expression_summary(gene_id)`` - The summary the site cached for one \
gene. When the result carries ``unavailableReason``, say that the site has no \
summary for the gene.

A control test runs only on a control set attached to this conversation, \
named by the id ``list_control_sets`` gives it. When the work order names a \
control set, test the root with it once. With no attached set, run no control \
test. State a control count or a control gene id only as a test of this turn \
filed it; the runtime refuses any other once.

GO, pathway and word enrichment are analyses the site runs on a step, from its \
result page; the evidence card links it. They are not checks you run.

Do NOT modify the strategy. Do NOT explore the catalog or create plans.

## Output - the VerificationDelta contract

Return exactly one ``VerificationDelta`` wrapping a ``VerificationDigest``:

- ``digest.prose`` (required): what the records you read look like and what \
the runtime's checks found. Restate a number only as a check or a read of this \
turn states it. State no verdict of your own.
- ``digest.handoff_to`` (optional): ``build`` or ``frame``, the phase a failed \
check points to.
- ``digest.key_findings`` (optional, <=10): one-line facts the user should \
walk away with.
- ``digest.review``: ``sampled_genes`` and ``sources``, as above.
- ``digest.remember`` (optional, <=5): durable knowledge memories to \
autowrite. Each needs ``name``, ``summary``, ``content``, optional ``tags``.

``prose`` and ``key_findings`` are rendered as Markdown. Wrap every literal \
identifier in backticks, **bold** the key number in a finding, and keep each \
``key_finding`` to one line without a leading bullet.
"""
)

VERIFICATION_MODEL = DEFAULT_MODEL_ID

VerificationAgent = Agent[AgentDeps, VerificationDelta | DeferredToolRequests]


def pinned_researcher_request(ctx: RunContext[AgentDeps]) -> str | None:
    """Every message of the request in the researcher's own words, numbered."""
    scope = ctx.deps.verification_scope
    if not scope.messages:
        return None
    return "\n".join(
        [
            "## The researcher's request",
            *(f"{number}. {text}" for number, text in enumerate(scope.messages, 1)),
        ]
    )


def build_verification_agent() -> VerificationAgent:
    """A verification agent for one dispatch.

    Each dispatch gets its own instance, so an override entered for one run
    never reaches another.
    """
    stable = StableInstructions[AgentDeps]()
    agent: VerificationAgent = Agent(
        VERIFICATION_MODEL,
        output_type=[VerificationDelta, DeferredToolRequests],
        deps_type=AgentDeps,
        instructions=_VERIFICATION_INSTRUCTIONS,
        toolsets=[
            build_toolset(),
            build_scratchpad_toolset(
                guidance=PATHFINDER_SCRATCHPAD_GUIDANCE,
                promoted_kind=PROMOTED_NOTE_KIND,
            ),
            turn_tool_sources,
        ],
        capabilities=agent_capabilities(
            [
                ToolResilience(search_lookup_tools=SEARCH_LOOKUP_TOOLS),
                AllowedTools[AgentDeps](rules=[withhold_scratchpad_tools]),
                stable,
                *(ProcessHistory[AgentDeps](p) for p in HISTORY_PROCESSORS),
            ],
        ),
        retries=3,
        description="Reads sample records of a strategy the runtime checked",
        name="verification",
        defer_model_check=True,
    )
    for fn in (
        base_system_prompt,
        pinned_researcher_request,
        pinned_graph_state,
        pinned_user_memories,
        pinned_conversation_so_far,
        pinned_scratchpad,
        pinned_ledger,
        pinned_discovered_searches,
        pinned_run_budget,
    ):
        agent.instructions(stable.section(fn))
    agent.output_validator(hold_the_digest_to_the_evidence)
    return agent
