from __future__ import annotations

from uuid import uuid4

import pytest
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree

from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead.ledger_render import render_frame_full
from strategist.ai.lead.ledger_sections import FrameSection
from strategist.ai.lead.turn_facts import turn_facts
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.operator_reads import OperatorRead, OperatorReading
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.domain.turn_facts import StepFact
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state


def _spec(read: OperatorRead | None) -> OperationalSpec:
    return OperationalSpec(
        criteria=[
            Criterion(id=cid, text=cid, search_name="GenesByText")
            for cid in ("step_a", "step_b")
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.UNION,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="step_a"),
                    StructureNode(kind="leaf", criterion_id="step_b"),
                ],
            )
        ),
        operator_reads=[]
        if read is None
        else [
            OperatorReading(
                criteria=["step_a", "step_b"],
                built=CombineOp.UNION,
                read=read,
                read_operator=CombineOp.UNION,
            )
        ],
    )


def _session() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Kinases", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_join",
            search_name="boolean_question",
            operator=CombineOp.UNION,
            primary_input=StrategyStepNode(id="step_a", search_name="GenesByText"),
            secondary_input=StrategyStepNode(id="step_b", search_name="GenesByText"),
        )
    )
    graph.recompute_roots()
    session.graph = graph
    return session


def _join(read: OperatorRead | None) -> StepFact:
    spec = _spec(read)
    state = pipeline_state(
        user_message_id=uuid4(),
        domain=StrategyDomainState(operational_spec=spec, answered_spec=spec),
    )
    steps = turn_facts(lead_deps(state, strategy_session=_session())).steps
    return next(step for step in steps if step.step_id == "step_join")


@pytest.mark.parametrize(
    ("read", "source", "line"),
    [
        ("agrees", "stated", "operator stated by the researcher"),
        ("picked", "card", "operator picked by the researcher on a card"),
        ("unsure", "chosen", "operator chosen by the assistant"),
        (None, "chosen", "operator chosen by the assistant"),
    ],
)
def test_a_combine_step_names_who_chose_its_operator(
    read: OperatorRead | None, source: str, line: str
) -> None:
    join = _join(read)

    assert (join.operator_source, line in join.lines()[0]) == (source, True)


def test_a_search_step_names_no_operator_source() -> None:
    spec = _spec("agrees")
    state = pipeline_state(
        user_message_id=uuid4(),
        domain=StrategyDomainState(operational_spec=spec, answered_spec=spec),
    )
    steps = turn_facts(lead_deps(state, strategy_session=_session())).steps

    assert [s.operator_source for s in steps if s.step_id != "step_join"] == [
        None,
        None,
    ]


def test_the_ledger_names_who_chose_each_combine() -> None:
    rendered = render_frame_full(FrameSection(spec=_spec("agrees")))

    assert "- UNION over step_a, step_b: stated by the researcher" in rendered
