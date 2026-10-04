"""How the Lead hands one dispatch to a sub-agent.

The deps the sub-agent runs under, the Lead call the dispatch belongs to, and
the two ways a dispatch ends before it returns a delta.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import NoReturn

from pydantic_ai import RunContext
from pydantic_ai.exceptions import CallDeferred, ModelRetry, ToolFailed

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps, one_toolset
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.retrieval_toolset import recording_retrievals
from pathfinder.ai.lead.sub_agent_stream import SubAgentApprovalWait, SubAgentResume
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, SubAgentDurablePark
from pathfinder.domain.strategy.constraints import (
    combination_requirements_from,
    organism_hints_from,
)
from pathfinder.domain.strategy.named_combine import NamedCombine, stated_operators
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.orthology_request import OrthologyRequest
from pathfinder.domain.strategy.spec_diff import SpecDiff, diff_specs
from pathfinder.domain.strategy.spec_reconciliation import (
    spec_without_pending_analyses,
)


def framing_goal(state: PipelineState) -> str:
    """The text a fresh spec is framed from.

    A clarification answers a request that was made earlier, so the pass reads
    the original request and the answer to it, in that order.
    """
    original = state.domain.original_request
    # The text alone: a sub-agent binds searches and reads no attached file.
    latest = state.user_prompt
    if not original or original == latest:
        return latest or original
    if not latest:
        return original
    return f"{original}\n\nThe user then clarified: {latest}"


def agent_deps_for(deps: LeadDeps) -> AgentDeps:
    state = deps.state
    runtime = deps.runtime
    ledger = derive_ledger(state, deps.intent, phase_stop=deps.last_phase_stop)
    requirements = [*state.domain.requirements, *ledger.constraints.recommended]
    found = state.domain.spec_before_dispatch
    return AgentDeps(
        site_id=runtime.site_id,
        user_id=runtime.user_id,
        strategy_session=runtime.strategy_session,
        tool_sources=recording_retrievals(one_toolset(runtime.tool_sources), deps),
        agent_state=AgentToolState(
            discovered_searches=dict(state.domain.discovered_searches),
            # The draft is a copy, so a pass that binds nothing leaves the
            # committed spec exactly as the turn found it.
            operational_spec_draft=(
                state.domain.operational_spec.model_copy(deep=True)
                if state.domain.operational_spec is not None
                else OperationalSpec(goal=framing_goal(state))
            ),
            organism_hints=organism_hints_from(requirements),
            combination_requirements=combination_requirements_from(requirements),
            named_combine=NamedCombine.read(state.user_prompt),
            held_structure=None if found is None else found.structure,
            orthology_request=OrthologyRequest.read(state.user_prompt),
            stated_operators=stated_operators(state.user_prompt),
            stated_requirements=list(state.domain.requirements),
            created_gene_sets=deps.created_gene_sets,
            request_messages=state.researcher_messages(),
            turn_counts=deps.turn_counts,
        ),
        turn_markers=state.turn_markers,
        ledger_summary=ledger.render_summary(),
        cancel_event=runtime.cancel_event,
        memory_store=runtime.memory_store,
        retrieved_memories=deps.retrieved_memories,
        conversation_id=state.conversation_id,
        db_session_factory=runtime.db_session_factory,
        user_prompt=state.request_the_thread_answers,
    )


def inner_context(ctx: RunContext[LeadDeps]) -> RunContext[AgentDeps]:
    """The Lead's context, narrowed to the deps a standalone tool takes.

    It is the same run: the usage it counts against and the budget that run
    enforces are the outer ones.
    """
    return RunContext(
        deps=agent_deps_for(ctx.deps),
        model=ctx.model,
        usage=ctx.usage,
        usage_limits=ctx.usage_limits,
        tool_call_id=ctx.tool_call_id,
    )


def dispatch_call_id(ctx: RunContext[LeadDeps]) -> str:
    """The Lead's tool_call_id for the active sub-agent dispatch.
    Always present when invoked through the Lead's toolset; defensively
    returns an empty string if missing so we never crash on telemetry."""
    return ctx.tool_call_id or ""


def defer_dispatch(
    deps: LeadDeps,
    tool_call_id: str,
    wait: SubAgentApprovalWait,
) -> NoReturn:
    """End the Lead's run deferred so the sub-agent's parked call is answered.

    The dispatch call carries the suspended run, so the answer re-enters it
    whether the user or the worker produced it.
    """
    if wait.durable:
        deps.pending_sub_agent_durables[tool_call_id] = SubAgentDurablePark(
            pending=wait.pending,
            deferrals=dict(wait.durable),
        )
    else:
        deps.pending_sub_agent_approvals[tool_call_id] = wait.pending
    raise CallDeferred


def record_the_spec_the_dispatch_found(
    deps: LeadDeps, *, resume: SubAgentResume | None
) -> None:
    """Record the committed spec this dispatch plans and restores against.

    A resumed dispatch keeps the record it parked with, so the answer to a
    question is measured against the spec the parked pass started from. The
    turn's own refresh has already brought that record to the live strategy.
    """
    if resume is not None:
        return
    found = deps.state.domain.operational_spec
    deps.state.domain.spec_before_dispatch = (
        None if found is None else found.model_copy(deep=True)
    )


def the_edit_the_strategy_owes(
    state: PipelineState, found: OperationalSpec
) -> tuple[OperationalSpec, SpecDiff]:
    """The spec the strategy answers to, and what ``found`` states beyond it.

    A criterion an earlier pass framed and never pushed is the edit's to build,
    so every pass of the edit is shown it. A criterion waiting for its analysis
    is the EDA tools' to build, so no push carries it.
    """
    answered = state.domain.answered_spec or found
    return answered, diff_specs(
        spec_without_pending_analyses(answered), spec_without_pending_analyses(found)
    )


def refuse_and_keep_what_it_bound(
    deps: LeadDeps, message: str, *, refused: Collection[str] = ()
) -> NoReturn:
    """Reject the pass, and keep each bound criterion the dispatch did not find
    and the refusal does not name.

    Every criterion the dispatch found is put back as it was found, so the
    retry keeps new work and never a change to what was there.
    """
    before = deps.state.domain.spec_before_dispatch
    draft = deps.state.domain.operational_spec
    if before is not None and draft is not None:
        found = {c.id for c in before.criteria}
        kept = before.model_copy(deep=True)
        kept.criteria += [
            c.model_copy(deep=True)
            for c in draft.criteria
            if c.bound and c.id not in found and c.id not in refused
        ]
        deps.state.domain.operational_spec = kept
    raise ModelRetry(message)


def refuse_and_restore(deps: LeadDeps, message: str) -> NoReturn:
    """Reject the pass and put back the spec the dispatch found.

    The sub-agent writes into the shared spec as it goes, so a refusal that
    left the draft in place would show the retry a workspace missing the very
    criterion it has to preserve.
    """
    _restore_the_found_spec(deps)
    raise ModelRetry(message)


def refuse_without_retry(deps: LeadDeps, message: str) -> NoReturn:
    """Fail the call for good and put back the spec the dispatch found."""
    _restore_the_found_spec(deps)
    raise ToolFailed(message)


def _restore_the_found_spec(deps: LeadDeps) -> None:
    before = deps.state.domain.spec_before_dispatch
    deps.state.domain.operational_spec = (
        None if before is None else before.model_copy(deep=True)
    )
