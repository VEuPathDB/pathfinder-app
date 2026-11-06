"""A criterion read back from a strategy carries the radio pairs its search declares."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection
from typing import Any

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, flatten_tree
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import answered_strategy, pre_turn
from pathfinder.ai.lead.answered_strategy import the_changes_written_outside
from pathfinder.ai.lead.pre_turn import stated_spec_of
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.services.strategies import record_classes
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state

_INTERPRO = "GenesByInterproDomain"
_PAIRS = {_INTERPRO: {"domain_typeahead": "domain_accession"}}


@pytest.fixture(autouse=True)
def _catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _resolver(_site_id: str) -> Callable[[str], Awaitable[str | None]]:
        async def _listed_under(_search_name: str) -> str | None:
            return "transcript"

        return _listed_under

    async def _sheets(**_kwargs: Any) -> dict[str, list[ParameterInfo]]:
        return {}

    async def _marks(_site_id: str, _searches: Collection[str]) -> dict[str, str]:
        return {}

    async def _pairs(
        _site_id: str, searches: Collection[str]
    ) -> dict[str, dict[str, str]]:
        return {name: pairs for name, pairs in _PAIRS.items() if name in searches}

    monkeypatch.setattr(record_classes, "make_record_type_resolver", _resolver)
    for module in (answered_strategy, pre_turn):
        monkeypatch.setattr(module, "sheet_params_for_searches", _sheets)
        monkeypatch.setattr(module, "organism_parameters", _marks)
        monkeypatch.setattr(module, "radio_pairs_of", _pairs)


def _step(search_name: str) -> StrategyStepNode:
    return StrategyStepNode(
        id="step_domain",
        search_name=search_name,
        parameters={"domain_accession": StringValue(value="PF00069")},
    )


async def test_a_strategy_read_at_turn_entry_states_the_pairs() -> None:
    spec = await stated_spec_of(
        StrategyAst(record_type="transcript", root=_step(_INTERPRO)),
        site_id="plasmodb",
        goal="kinase domain genes",
    )

    assert [(c.search_name, c.radio_pairs) for c in spec.criteria] == [
        (_INTERPRO, _PAIRS[_INTERPRO])
    ]


async def test_a_search_moved_outside_takes_the_pairs_of_its_new_search() -> None:
    held = OperationalSpec(
        goal="kinase domain genes",
        criteria=[
            Criterion(id="step_domain", text="kinase genes", search_name="GenesByText")
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="step_domain")
        ),
    )
    state = pipeline_state(
        "plasmodb",
        domain=StrategyDomainState(
            operational_spec=held,
            answered_spec=held,
            answered_graph=StrategyAst(
                record_type="transcript", root=_step("GenesByText")
            ),
        ),
    )
    graph = StrategyGraph(graph_id="g1", name="kinases", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(_step(_INTERPRO))
    graph.recompute_roots()

    await the_changes_written_outside(state, site_id="plasmodb", graph=graph)

    spec = state.domain.operational_spec
    assert spec is not None
    assert [(c.search_name, c.radio_pairs) for c in spec.criteria] == [
        (_INTERPRO, _PAIRS[_INTERPRO])
    ]
