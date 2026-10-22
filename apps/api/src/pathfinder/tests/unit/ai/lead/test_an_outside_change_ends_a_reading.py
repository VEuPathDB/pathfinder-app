"""A step the researcher changed on the site ends the reading its criterion
held, and the reading's stand-in with it."""

from __future__ import annotations

from collections.abc import Collection

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, flatten_tree
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import answered_strategy
from pathfinder.ai.lead.answered_strategy import the_changes_written_outside
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    WithdrawnLifecycle,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.readings import AcceptedReading
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.tests._support.sheets import visible_sheet
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state

_TEXT, _WORDS = "GenesByText", "GenesByWords"
_READING = "Every kinase named in the product"
_STAND_IN = Constraint(
    kind=ConstraintKind.OTHER,
    requested_value=_READING,
    label="Which kinases?",
    source=ConstraintSource.USER_EXPLICIT,
)


@pytest.fixture(autouse=True)
def _sheets(monkeypatch: pytest.MonkeyPatch) -> None:
    published = {
        _TEXT: visible_sheet(["text_expression"]),
        _WORDS: visible_sheet(["words"]),
    }

    async def _read(
        *, site_id: str, record_type: str | None, search_names: Collection[str]
    ) -> dict[str, list[ParameterInfo]]:
        del site_id, record_type
        return {name: published[name] for name in search_names}

    async def _marks(_site_id: str, _searches: Collection[str]) -> dict[str, str]:
        return {}

    monkeypatch.setattr(answered_strategy, "sheet_params_for_searches", _read)
    monkeypatch.setattr(answered_strategy, "organism_parameters", _marks)


def _step(search_name: str, name: str, value: str) -> StrategyStepNode:
    return StrategyStepNode(
        id="kin", search_name=search_name, parameters={name: StringValue(value=value)}
    )


def _graph(root: StrategyStepNode) -> StrategyGraph:
    graph = StrategyGraph(graph_id="g1", name="kinases", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    return graph


def _domain() -> StrategyDomainState:
    spec = OperationalSpec(
        goal="kinases",
        criteria=[
            Criterion(
                id="kin",
                text="kinases",
                search_name=_TEXT,
                resolved_params={
                    "text_expression": BoundValue(
                        value=StringValue(value="kinase"), source="card"
                    )
                },
                accepted_reading=AcceptedReading(
                    reading=_READING,
                    params={"text_expression": "kinase"},
                    stand_in=_STAND_IN.key,
                ),
            )
        ],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id="kin")),
    )
    return StrategyDomainState(
        operational_spec=spec,
        answered_spec=spec,
        answered_graph=StrategyAst(
            record_type="transcript", root=_step(_TEXT, "text_expression", "kinase")
        ),
        requirements=[_STAND_IN],
    )


@pytest.mark.parametrize(
    "live",
    [
        _step(_WORDS, "words", "kinase"),
        _step(_TEXT, "text_expression", "phosphatase"),
    ],
)
async def test_a_change_on_the_site_ends_the_reading_and_its_stand_in(
    live: StrategyStepNode,
) -> None:
    state = pipeline_state(domain=_domain())

    await the_changes_written_outside(state, site_id="plasmodb", graph=_graph(live))

    spec = state.domain.operational_spec
    assert spec is not None
    assert [c.held_reading for c in spec.criteria] == [None]
    assert state.domain.requirements == []
    assert [(r.constraint, r.lifecycle) for r in state.domain.retired_requirements] == [
        (_STAND_IN, WithdrawnLifecycle(turn_id=""))
    ]


async def test_a_change_elsewhere_keeps_the_reading_and_its_stand_in() -> None:
    state = pipeline_state(domain=_domain())

    await the_changes_written_outside(
        state,
        site_id="plasmodb",
        graph=_graph(_step(_TEXT, "text_expression", "kinase")),
    )

    assert state.domain.requirements == [_STAND_IN]
