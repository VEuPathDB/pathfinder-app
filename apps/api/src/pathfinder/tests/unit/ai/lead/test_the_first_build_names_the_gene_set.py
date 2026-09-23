"""The gene set a first build imports is named by the goal it was framed from.

The thread has no title until its first turn ends, so the set takes the goal
and follows the title once the thread has one.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import RunContext
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import sub_agent_dispatch
from pathfinder.ai.lead.sub_agent_dispatch import build_strategy
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state


def _ctx(goal: str, interpreted: str) -> RunContext[LeadDeps]:
    spec = OperationalSpec(
        goal=goal,
        interpreted_goal=interpreted,
        criteria=[
            Criterion(id="step_text", text="protease text", search_name="GenesByText"),
            Criterion(id="step_go", text="proteolysis GO", search_name="GenesByGoTerm"),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="step_text"),
                    StructureNode(kind="leaf", criterion_id="step_go"),
                ],
            )
        ),
    )
    session = StrategySession(site_id="plasmodb")
    session.graph = StrategyGraph(
        graph_id="g1", name="New Conversation", site_id="plasmodb"
    )
    state = pipeline_state(
        user_prompt=goal, domain=StrategyDomainState(operational_spec=spec)
    )
    return run_context_for(lead_deps(state, strategy_session=session))


@pytest.mark.parametrize(
    ("goal", "interpreted", "expected"),
    [
        ("proteases", "", "proteases"),
        (
            "proteases\n\nThe user then clarified: in P. falciparum",
            "",
            "proteases",
        ),
        (
            "proteases",
            (
                "Proteases expressed in gametocytes of P. falciparum 3D7 that "
                "carry a signal peptide"
            ),
            "Proteases expressed in gametocytes of P. falciparum 3D7 that",
        ),
    ],
)
async def test_the_first_build_names_the_gene_set_by_the_goal(
    monkeypatch: pytest.MonkeyPatch, goal: str, interpreted: str, expected: str
) -> None:
    names: list[str] = []

    async def _fake_build(**kwargs: Any) -> BuildOutcome:
        return BuildOutcome(
            pushed_step_ids=[kwargs["root"].id], wdk_strategy_id=330679883
        )

    async def _import(**kwargs: Any) -> None:
        names.append(kwargs["name"])

    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _fake_build)
    monkeypatch.setattr(sub_agent_dispatch, "import_gene_set_for_conversation", _import)
    monkeypatch.setattr(
        sub_agent_dispatch, "get_stream_writer", lambda: lambda _p: None
    )

    await build_strategy(_ctx(goal, interpreted))

    assert names == [expected]
