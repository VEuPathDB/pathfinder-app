"""The Lead agent, which owns the user-facing voice and calls the sub-agent tools.

The Lead reads the typed ledger after each call and decides the next tool. A phase is
a tool the Lead invokes, not a node in a fixed graph.
"""

from __future__ import annotations

from typing import Any, Literal

from assistant_core.conversation.history import HISTORY_PROCESSORS
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from pydantic_ai import Agent, DeferredToolRequests, RunContext, Tool
from pydantic_ai.capabilities import PrepareTools, ProcessHistory, Thinking
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.toolsets import AbstractToolset

from pathfinder.ai.agents._instructions import (
    pinned_run_budget,
    pinned_user_memories,
)
from pathfinder.ai.capabilities.refusals import ServiceRefusalRetry
from pathfinder.ai.graph.runtime import one_toolset
from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.dispatch_messages import (
    blamed_the_site_message,
    unrecorded_question_message,
    unverified_build_message,
)
from pathfinder.ai.lead.edit_dispatch import edit_strategy
from pathfinder.ai.lead.frame_dispatch import frame_problem
from pathfinder.ai.lead.guarantees import machine_guarantees_pin
from pathfinder.ai.lead.intent_gate import apply_tool_preconditions
from pathfinder.ai.lead.lead_consult import consult_user
from pathfinder.ai.lead.lead_pins import (
    pinned_eda_sheet,
    pinned_ledger_summary,
    pinned_operational_spec,
    pinned_turn_briefing,
    pinned_user_intent,
    pinned_user_prompt,
)
from pathfinder.ai.lead.lead_tools import (
    classify_user_intent,
    clear_strategy,
    create_workbench_gene_set,
    get_live_strategy_state,
    list_workbench_gene_sets,
    read_ledger_section,
    remember,
)
from pathfinder.ai.lead.ledger import blamed_the_site
from pathfinder.ai.lead.sub_agent_dispatch import (
    build_strategy,
    recover_failed_steps,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verify_dispatch import verify_strategy
from pathfinder.ai.tools.standalone.control_sets import (
    build_control_set,
    import_control_ids_from_gene_set,
    import_control_ids_from_strategy,
    list_control_sets,
)
from pathfinder.ai.tools.standalone.scored_comparison import compare_variants_scored
from pathfinder.ai.tools.standalone.variant_comparison import compare_search_variants
from pathfinder.ai.tools.toolsets import eda
from pathfinder.domain.strategy.constraints import OpenQuestion

LeadTurnState = Literal["await_user", "complete"]


def turn_tool_sources(ctx: RunContext[LeadDeps]) -> AbstractToolset[Any] | None:
    """The servers this turn resolved, as the tools of this run."""
    return one_toolset(ctx.deps.runtime.tool_sources)


class LeadResponse(CamelModel):
    """The Lead's final user-facing turn output.

    ``prose`` is rendered to the user verbatim (no upstream/downstream
    translation). ``next_state`` tells the dispatcher whether the turn is
    paused waiting on the user (``await_user``) or fully resolved
    (``complete`` - typically after a successful verification).
    """

    prose: str = Field(
        max_length=4000,
        description=(
            "User-facing reply for this turn. Plain markdown. Do NOT "
            "include sub-agent log noise - synthesize from the Ledger."
        ),
    )
    next_state: LeadTurnState = "await_user"
    asked_questions: list[OpenQuestion] = Field(
        default_factory=list,
        max_length=8,
        description=(
            "One entry per question this reply asks the user, carrying the "
            "value you recommend for it and the dimension it decides. A "
            "question you ask in prose and leave out of here is one the next "
            "turn has to ask again."
        ),
    )


LeadAgent = Agent[LeadDeps, LeadResponse | DeferredToolRequests]


def verify_what_this_turn_built(
    ctx: RunContext[LeadDeps],
    output: LeadResponse | DeferredToolRequests,
) -> LeadResponse | DeferredToolRequests:
    """Refuse the first answer of a turn that built and never verified.

    The precondition gate offers ``verify_strategy``; a gate cannot compel the
    call. The refusal is asked once per turn, so a second answer that states
    why a check is impossible still reaches the user.
    """
    markers = ctx.deps.state.turn_markers
    if (
        not markers.built
        or markers.verified
        or markers.verification_dispatched
        or markers.verification_nudged
    ):
        return output
    markers.verification_nudged = True
    raise ModelRetry(
        unverified_build_message(ctx.deps.state.domain.last_build_outcome),
    )


def refuse_blaming_the_site(
    ctx: RunContext[LeadDeps],
    output: LeadResponse | DeferredToolRequests,
) -> LeadResponse | DeferredToolRequests:
    """Refuse a reply that attributes an internal stop to VEuPathDB.

    A pass that ran out of calls is this turn's own limit. The refusal names
    that limit, so the rewrite states it instead of asking the user to wait for
    a site that reported no failure. It is asked once per turn.
    """
    if not isinstance(output, LeadResponse) or ctx.deps.site_blame_refused:
        return output
    ledger = derive_ledger(ctx.deps.state, ctx.deps.intent)
    blame = blamed_the_site(output.prose, build=ledger.build)
    if blame is None:
        return output
    ctx.deps.site_blame_refused = True
    raise ModelRetry(blamed_the_site_message(blame, ctx.deps.last_phase_stop))


def refuse_an_unrecorded_question(
    ctx: RunContext[LeadDeps],
    output: LeadResponse | DeferredToolRequests,
) -> LeadResponse | DeferredToolRequests:
    """Refuse a reply that asks the user something and records no question.

    The next turn binds what the reply recorded, so a question only the prose
    carries is asked again. A turn that framed nothing asks for no value, so
    the refusal is asked of a framing turn, once.
    """
    if not isinstance(output, LeadResponse) or ctx.deps.unrecorded_question_refused:
        return output
    if not ctx.deps.state.turn_markers.framed:
        return output
    if output.next_state != "await_user" or output.asked_questions:
        return output
    if "?" not in output.prose:
        return output
    ctx.deps.unrecorded_question_refused = True
    raise ModelRetry(unrecorded_question_message())


LEAD_MODEL = "openai:gpt-5.6-luna"


def build_lead_agent() -> LeadAgent:
    """A Lead agent for one turn.

    Each turn gets its own instance, so a per-turn model override never
    reaches another turn.
    """
    agent: LeadAgent = Agent(
        LEAD_MODEL,
        output_type=[LeadResponse, DeferredToolRequests],
        deps_type=LeadDeps,
        instructions=LEAD_INSTRUCTIONS,
        tools=[
            Tool(classify_user_intent),
            Tool(remember),
            Tool(create_workbench_gene_set),
            Tool(list_workbench_gene_sets),
            Tool(read_ledger_section),
            Tool(get_live_strategy_state),
            Tool(frame_problem),
            Tool(edit_strategy),
            Tool(build_strategy),
            Tool(recover_failed_steps),
            Tool(verify_strategy),
            Tool(compare_search_variants),
            Tool(build_control_set),
            Tool(list_control_sets),
            Tool(import_control_ids_from_gene_set),
            Tool(import_control_ids_from_strategy),
            Tool(compare_variants_scored),
            Tool(clear_strategy, requires_approval=True),
            Tool(consult_user, requires_approval=True),
        ],
        toolsets=[eda.build_toolset(), turn_tool_sources],
        capabilities=[
            ServiceRefusalRetry[LeadDeps](),
            Thinking(effort="medium"),
            PrepareTools[LeadDeps](apply_tool_preconditions),
            *(ProcessHistory[LeadDeps](p) for p in HISTORY_PROCESSORS),
        ],
        retries=3,
        description="The user's voice - orchestrates sub-agents via the Ledger",
        name="lead",
        defer_model_check=True,
    )
    for fn in (
        pinned_user_memories,
        pinned_user_prompt,
        pinned_user_intent,
        pinned_operational_spec,
        pinned_eda_sheet,
        pinned_ledger_summary,
        pinned_run_budget,
    ):
        agent.instructions(fn)
    agent.instructions(machine_guarantees_pin(agent.toolsets))
    agent.instructions(pinned_turn_briefing)
    agent.output_validator(verify_what_this_turn_built)
    agent.output_validator(refuse_blaming_the_site)
    agent.output_validator(refuse_an_unrecorded_question)
    return agent
