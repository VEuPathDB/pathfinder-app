"""A computed comparison's group ids outlive the turn while a card names its
handle, so the save the researcher approves later reads them with no rebuild."""

from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import PendingApproval
from langgraph.runtime import Runtime

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph import nodes
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, apply_agent_state
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.ai.tools.standalone.orthomcl_expressions import (
    ComputedComparison,
    build_phyletic_expression,
)
from pathfinder.tests._support.group_list_site import served_group_list
from pathfinder.tests._support.orthomcl_clouds import served_genus_clouds
from pathfinder.tests._support.orthomcl_counts import SITE
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context
from pathfinder.tests.unit.ai.tools.test_a_compare_past_the_caps_is_computed import (
    genus_mean,
)

_QUESTION = "groups with more proteins per genome in Toxoplasma than Plasmodium"


async def _framed() -> tuple[LeadDeps, ComputedComparison]:
    deps = lead_deps(pipeline_state(SITE, user_message_id=uuid4()))
    state = AgentToolState()
    with served_genus_clouds():
        result = await build_phyletic_expression(
            agent_run_context(site_id=SITE, agent_state=state), genus_mean()
        )
    apply_agent_state(deps, agent_run_context(site_id=SITE, agent_state=state).deps)
    return deps, returned(result, ComputedComparison)


async def _finalized(deps: LeadDeps) -> StrategyDomainState:
    command = await nodes.finalize_turn_node(
        deps.state, cast("Runtime[Context]", Runtime(context=None))
    )
    update = command.update or {"domain": deps.state.domain}
    assert isinstance(update, dict)
    domain = update["domain"]
    assert isinstance(domain, StrategyDomainState)
    return domain


async def _saved(
    deps: LeadDeps, handle: str, monkeypatch: pytest.MonkeyPatch
) -> list[list[str]]:
    agent = agent_deps_for(deps, call_id="call_save")
    with served_group_list(monkeypatch, counted=7364) as site:
        await set_criterion(
            run_context_for(agent, "call_save"),
            criterion_id="c_more_in_toxo",
            text=_QUESTION,
            role="seed",
            computed_groups=handle,
        )
    [criterion] = agent.agent_state.operational_spec_draft.criteria
    assert (criterion.search_name, criterion.result_count) == (
        "GroupsByNameList",
        7364,
    )
    return site.uploaded


async def test_a_save_approved_in_the_next_turn_reads_the_held_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps, computed = await _framed()
    deps.state.pending_approval = PendingApproval(
        phase="lead",
        tool_call_id="call_consult",
        tool_name="consult_user",
        tool_args={"question": f"Save these groups ({computed.handle}) as a step?"},
    )
    kept = await _finalized(deps)
    later = lead_deps(pipeline_state(SITE, domain=kept, user_message_id=uuid4()))

    uploaded = await _saved(later, computed.handle, monkeypatch)

    assert (sorted(kept.computed_comparisons), [len(ids) for ids in uploaded]) == (
        [computed.handle],
        [7364],
    )


async def test_a_second_framing_pass_of_the_turn_saves_the_first_ones_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps, computed = await _framed()

    uploaded = await _saved(deps, computed.handle, monkeypatch)

    assert [len(ids) for ids in uploaded] == [7364]


async def test_a_comparison_no_card_names_is_dropped_at_the_turn_end() -> None:
    deps, computed = await _framed()
    deps.state.pending_approval = PendingApproval(
        phase="lead",
        tool_call_id="call_consult",
        tool_name="consult_user",
        tool_args={"question": "Which genus?"},
    )

    kept = await _finalized(deps)

    assert (kept.computed_comparisons, [s.id for s in kept.statistics]) == (
        {},
        [computed.fact_id],
    )
