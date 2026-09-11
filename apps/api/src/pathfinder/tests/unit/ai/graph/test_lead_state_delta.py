"""What the Lead node writes back to the graph state.

The strategy fields live on one ``domain`` channel now, so the node writes
that whole object rather than a field per key.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from pathfinder.ai.agents.state import SearchOverview
from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph._lead_delta import _build_state_delta
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.lead_agent import LeadResponse
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.domain.strategy.staleness import StaleBuild
from pathfinder.tests._support.database import no_database


def _overview() -> SearchOverview:
    return SearchOverview(
        search_name="GenesByTaxon",
        display_name="Genes by Taxon",
        record_type="transcript",
        description="",
        parameter_names=["organism"],
        required_params=["organism"],
    )


def _state(domain: StrategyDomainState | None = None) -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        domain=domain or StrategyDomainState(),
    )


def _deps(state: PipelineState, intent: UserIntent | None = None) -> LeadDeps:
    return LeadDeps(
        state=state,
        intent=intent,
        runtime=Context(
            site_id="plasmodb",
            user_id=uuid4(),
            strategy_session=StrategySession(site_id="plasmodb"),
            db_session_factory=no_database,
            cancel_event=asyncio.Event(),
        ),
        retrieved_memories=[],
    )


def _delta(
    state: PipelineState,
    deps: LeadDeps,
    capture: _LeadRunCapture,
) -> dict[str, object]:
    return _build_state_delta(state=state, deps=deps, capture=capture, memories=[])


def test_the_strategy_fields_travel_on_one_domain_channel() -> None:
    state = _state()
    deps = _deps(state)
    delta = _delta(state, deps, _LeadRunCapture())

    assert set(delta) == {
        "domain",
        "retrieved_memories",
        "turn_total_tokens",
        "turn_total_cost_usd",
    }
    assert isinstance(delta["domain"], StrategyDomainState)


def test_the_intent_the_lead_classified_is_written_to_the_domain() -> None:
    intent = UserIntent(
        raw_text="find drug targets",
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="protein kinases",
    )
    state = _state()
    deps = _deps(state, intent)
    domain = _delta(state, deps, _LeadRunCapture())["domain"]

    assert isinstance(domain, StrategyDomainState)
    assert domain.user_intent == intent


def test_staleness_is_not_persisted() -> None:
    """It is measured against the live strategy at the start of every turn."""
    state = _state()
    deps = _deps(state)
    deps.state.domain.stale_build = StaleBuild(added_nodes=["s3"])
    domain = _delta(state, deps, _LeadRunCapture())["domain"]

    assert isinstance(domain, StrategyDomainState)
    assert domain.stale_build is None


def test_a_turn_without_a_lead_response_keeps_the_recorded_next_state() -> None:
    state = _state(StrategyDomainState(lead_next_state="complete"))
    deps = _deps(state)
    domain = _delta(state, deps, _LeadRunCapture())["domain"]

    assert isinstance(domain, StrategyDomainState)
    assert domain.lead_next_state == "complete"


def test_a_lead_response_sets_the_next_state() -> None:
    state = _state(StrategyDomainState(lead_next_state="complete"))
    deps = _deps(state)
    capture = _LeadRunCapture()
    capture.response = LeadResponse(prose="Anything else?", next_state="await_user")
    domain = _delta(state, deps, capture)["domain"]

    assert isinstance(domain, StrategyDomainState)
    assert domain.lead_next_state == "await_user"


def test_the_discovered_searches_map_is_copied_out_of_the_working_state() -> None:
    state = _state()
    deps = _deps(state)
    deps.state.domain.discovered_searches["GenesByTaxon"] = _overview()
    domain = _delta(state, deps, _LeadRunCapture())["domain"]

    assert isinstance(domain, StrategyDomainState)
    assert domain.discovered_searches == deps.state.domain.discovered_searches
    assert domain.discovered_searches is not deps.state.domain.discovered_searches


def test_the_turn_totals_accumulate_the_lead_and_its_sub_agents() -> None:
    state = _state().model_copy(update={"turn_total_tokens": 100})
    deps = _deps(state)
    capture = _LeadRunCapture()
    capture.tokens = 20
    capture.sub_agent_tokens = 5
    delta = _delta(state, deps, capture)

    assert delta["turn_total_tokens"] == 125
