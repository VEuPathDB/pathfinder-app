from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import RunContext
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

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
from pathfinder.domain.turn_facts import UnsavedSetFact
from pathfinder.platform.config import get_settings
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

CAP = get_settings().step_genes_cap


def _ctx() -> RunContext[LeadDeps]:
    spec = OperationalSpec(
        goal="singleton proteins",
        criteria=[
            Criterion(id="step_proteins", text="singletons", search_name="ByGroup")
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="step_proteins")
        ),
    )
    session = StrategySession(site_id="orthomcl")
    session.graph = StrategyGraph(graph_id="g1", name="Singletons", site_id="orthomcl")
    state = pipeline_state(
        "orthomcl",
        user_prompt="singleton proteins",
        domain=StrategyDomainState(operational_spec=spec),
    )
    return run_context_for(lead_deps(state, strategy_session=session))


def _serve(monkeypatch: pytest.MonkeyPatch, root_count: int) -> None:
    async def _push(**kwargs: Any) -> BuildOutcome:
        root = kwargs["root"]
        session: StrategySession = kwargs["deps"].strategy_session
        graph = session.get_graph(None)
        assert graph is not None
        graph.record_type = "sequence"
        graph.steps = flatten_tree(StrategyStepNode(id=root.id, search_name="ByGroup"))
        graph.recompute_roots()
        session.sync_state = WDKSyncState(
            step_counts={root.id: root_count},
            wdk_step_ids={root.id: 227_284_190},
            wdk_strategy_id=214_645_070,
        )
        return BuildOutcome(pushed_step_ids=[root.id], wdk_strategy_id=214_645_070)

    async def _import(**kwargs: Any) -> None:
        del kwargs

    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _push)
    monkeypatch.setattr(sub_agent_dispatch, "import_gene_set_for_conversation", _import)
    monkeypatch.setattr(
        sub_agent_dispatch, "get_stream_writer", lambda: lambda _p: None
    )


@pytest.mark.parametrize(
    ("root_count", "told"),
    [
        (523_795, UnsavedSetFact(count=523_795, cap=CAP, record_noun="protein")),
        (4_593, None),
    ],
)
async def test_the_build_delta_says_whether_the_result_was_saved(
    monkeypatch: pytest.MonkeyPatch, root_count: int, told: UnsavedSetFact | None
) -> None:
    _serve(monkeypatch, root_count)

    delta = await build_strategy(_ctx())

    assert delta.unsaved_gene_set == told
