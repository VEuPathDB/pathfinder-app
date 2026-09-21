"""The spec a turn derives from a live strategy states only the sheet's parameters.

A hidden WDK parameter reaches the stored step, and the edit tools refuse it,
so a criterion that stated it would cost a refused call on every edit.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import PendingApproval
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead import answered_strategy, pre_turn
from pathfinder.ai.lead.pre_turn import refresh_live_strategy_state
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    structure_criteria,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.database import no_database

_SEARCH = "GenesByRNASeqpfal3D7_Su_seven_stages_rnaSeq_RSRC"
_DATASET_URL = "https://PlasmoDB.org/a/app/record/dataset/DS_66f9e70b8a"


def _session() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Gametocyte kinases", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_7c2e770b",
            search_name=_SEARCH,
            parameters={
                "profileset_generic": StringValue(value="Pfal3D7 Su seven stages"),
                "dataset_url": StringValue(value=_DATASET_URL),
            },
        )
    )
    graph.recompute_roots()
    session.graph = graph
    return session


def _context(session: StrategySession) -> Context:
    return Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=session,
        db_session_factory=no_database,
        cancel_event=asyncio.Event(),
    )


def _state() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="use the gametocyte time course instead",
        domain=StrategyDomainState(),
    )


@pytest.fixture
def sheet(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _sheets(**_kwargs: Any) -> dict[str, frozenset[str]]:
        return {_SEARCH: frozenset({"profileset_generic"})}

    monkeypatch.setattr(pre_turn, "sheet_params_for_searches", _sheets)
    monkeypatch.setattr(answered_strategy, "sheet_params_for_searches", _sheets)


@pytest.mark.usefixtures("sheet")
async def test_a_hidden_parameter_is_not_stated_by_the_derived_criterion() -> None:
    refreshed = await refresh_live_strategy_state(_state(), _context(_session()))

    spec = refreshed.domain.operational_spec
    assert spec is not None
    criterion = spec.criteria[0]
    assert "dataset_url" not in criterion.resolved_params
    assert criterion.resolved_params["profileset_generic"] == StringValue(
        value="Pfal3D7 Su seven stages"
    )


def _split_spec_session() -> StrategySession:
    """A strategy of three leaves, one of which the spec will not name."""
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Essential kinases", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_c2",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=StrategyStepNode(
                id="step_c1",
                search_name=COMBINE_SEARCH_NAME,
                operator=CombineOp.INTERSECT,
                primary_input=StrategyStepNode(
                    id="step_kinase", search_name="GenesByInterproDomain"
                ),
                secondary_input=StrategyStepNode(
                    id="step_export",
                    search_name=_SEARCH,
                    display_name="berghei subset",
                    parameters={
                        "profileset_generic": StringValue(value="Pfal3D7"),
                        "dataset_url": StringValue(value=_DATASET_URL),
                    },
                ),
            ),
            secondary_input=StrategyStepNode(
                id="step_ortholog", search_name="GenesByOrthologPattern"
            ),
        ),
    )
    graph.recompute_roots()
    session.graph = graph
    return session


def _spec_without_the_export() -> OperationalSpec:
    return OperationalSpec(
        goal="essential kinases",
        criteria=[
            Criterion(
                id="step_kinase", text="PF00069", search_name="GenesByInterproDomain"
            ),
            Criterion(
                id="step_ortholog",
                text="no human ortholog",
                search_name="GenesByOrthologPattern",
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="step_kinase"),
                    StructureNode(kind="leaf", criterion_id="step_ortholog"),
                ],
            ),
        ),
    )


@pytest.mark.usefixtures("sheet")
async def test_a_live_step_the_spec_left_out_is_stated_before_the_turn_edits() -> None:
    """A step no criterion names is one the next edit would silently remove."""
    state = _state()
    state.domain.operational_spec = _spec_without_the_export()

    refreshed = await refresh_live_strategy_state(
        state, _context(_split_spec_session())
    )

    spec = refreshed.domain.operational_spec
    assert spec is not None
    assert sorted(c.id for c in spec.criteria) == [
        "step_export",
        "step_kinase",
        "step_ortholog",
    ]
    assert structure_criteria(spec.structure) == {
        "step_kinase",
        "step_export",
        "step_ortholog",
    }
    before = refreshed.domain.spec_before_turn
    assert before is not None
    assert structure_criteria(before.structure) == structure_criteria(spec.structure)


@pytest.mark.usefixtures("sheet")
async def test_the_stated_step_carries_the_sheet_parameters_only() -> None:
    state = _state()
    state.domain.operational_spec = _spec_without_the_export()

    refreshed = await refresh_live_strategy_state(
        state, _context(_split_spec_session())
    )

    spec = refreshed.domain.operational_spec
    assert spec is not None
    export = next(c for c in spec.criteria if c.id == "step_export")
    assert export.text == "berghei subset"
    assert export.resolved_params == {
        "profileset_generic": StringValue(value="Pfal3D7")
    }


def _planned(criterion_id: str) -> Criterion:
    return Criterion(
        id=criterion_id, text="secreted", search_name="GenesBySignalPeptide"
    )


@pytest.mark.usefixtures("sheet")
async def test_a_pending_criterion_at_the_plans_root_is_re_joined_over_the_tree() -> (
    None
):
    """The strategy states the built part; the plan keeps the criterion it owes."""
    state = _state()
    spec = _spec_without_the_export()
    spec.criteria.append(_planned("c_planned"))
    spec.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.INTERSECT,
            inputs=[
                StructureNode(kind="leaf", criterion_id="step_kinase"),
                StructureNode(kind="leaf", criterion_id="c_planned"),
            ],
        ),
    )
    state.domain.operational_spec = spec

    refreshed = await refresh_live_strategy_state(
        state, _context(_split_spec_session())
    )

    stated = refreshed.domain.operational_spec
    assert stated is not None
    assert structure_criteria(stated.structure) == {
        "step_kinase",
        "step_export",
        "step_ortholog",
        "c_planned",
    }


@pytest.mark.usefixtures("sheet")
async def test_a_plan_that_nested_its_pending_criterion_is_left_alone() -> None:
    """Only a plan that hangs what it owes off its root combine is re-joined."""
    state = _state()
    spec = _spec_without_the_export()
    spec.criteria.append(_planned("c_planned"))
    spec.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.INTERSECT,
            inputs=[
                StructureNode(
                    kind="combine",
                    operator=CombineOp.UNION,
                    inputs=[
                        StructureNode(kind="leaf", criterion_id="step_kinase"),
                        StructureNode(kind="leaf", criterion_id="c_planned"),
                    ],
                ),
                StructureNode(kind="leaf", criterion_id="step_ortholog"),
            ],
        ),
    )
    state.domain.operational_spec = spec

    refreshed = await refresh_live_strategy_state(
        state, _context(_split_spec_session())
    )

    stated = refreshed.domain.operational_spec
    assert stated is not None
    assert structure_criteria(stated.structure) == {
        "step_kinase",
        "c_planned",
        "step_ortholog",
    }


@pytest.mark.usefixtures("sheet")
async def test_a_turn_that_resumes_a_parked_call_states_every_live_step() -> None:
    """A parked call changes nothing until it returns, and the steps are live."""
    state = _state()
    parked = _spec_without_the_export()
    parked.criteria = [c for c in parked.criteria if c.id != "step_ortholog"]
    parked.structure = SpecStructure(
        root=StructureNode(kind="leaf", criterion_id="step_kinase"),
    )
    state.domain.operational_spec = parked
    state.domain.spec_before_turn = parked.model_copy(deep=True)
    state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_delete", tool_name="delete_step"
    )

    refreshed = await refresh_live_strategy_state(
        state, _context(_split_spec_session())
    )

    spec = refreshed.domain.operational_spec
    assert spec is not None
    assert sorted(c.id for c in spec.criteria) == [
        "step_export",
        "step_kinase",
        "step_ortholog",
    ]
    assert structure_criteria(spec.structure) == {
        "step_kinase",
        "step_export",
        "step_ortholog",
    }
