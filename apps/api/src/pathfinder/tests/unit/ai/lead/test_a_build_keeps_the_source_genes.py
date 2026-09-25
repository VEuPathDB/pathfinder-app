"""A build refuses an orthology round trip that would not keep the source genes."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import ModelRetry, RunContext

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import sub_agent_dispatch
from pathfinder.ai.lead.sub_agent_dispatch import build_strategy
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.domain.strategy._orthology import (
    round_trip_spec,
    seed_node,
    trip,
)


def _ctx(spec: OperationalSpec) -> RunContext[LeadDeps]:
    session = StrategySession(site_id="plasmodb")
    session.graph = StrategyGraph(graph_id="g1", name="Round trip", site_id="plasmodb")
    state = pipeline_state(
        user_prompt=spec.goal, domain=StrategyDomainState(operational_spec=spec)
    )
    return run_context_for(lead_deps(state, strategy_session=session))


async def test_a_round_trip_alone_is_refused_before_anything_is_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[str] = []

    async def _build(**kwargs: Any) -> BuildOutcome:
        built.append(kwargs["root"].id)
        return BuildOutcome()

    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _build)

    with pytest.raises(ModelRetry) as exc:
        await build_strategy(_ctx(round_trip_spec(trip(seed_node()))))

    assert "c_back (Transform by Orthology)" in str(exc.value)
    assert "Nothing was built" in str(exc.value)
    assert built == []
