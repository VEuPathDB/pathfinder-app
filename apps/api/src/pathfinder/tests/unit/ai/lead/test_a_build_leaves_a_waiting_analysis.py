"""A build mints the criteria a search realizes and leaves the ones that wait
for their analysis to the EDA tools."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    DisagreementThread,
    joined,
    leaf,
    session_holding,
)
from pathfinder.tests.unit.domain.strategy._analysis import DATASET, pending

_WAITING = "c_24h_vs_36_up"
_KINASES = Criterion(
    id="c_kinases", text="protein kinases", search_name="GenesByText", role="seed"
)


def _spec(*criteria: Criterion) -> OperationalSpec:
    leaves = [leaf(c.id) for c in criteria]
    return OperationalSpec(
        goal="kinases higher at 24 h than at 36 h",
        criteria=list(criteria),
        structure=SpecStructure(
            root=joined(CombineOp.INTERSECT, *leaves) if len(leaves) > 1 else leaves[0]
        ),
    )


def _empty_thread(
    monkeypatch: pytest.MonkeyPatch, spec: OperationalSpec
) -> DisagreementThread:
    session = session_holding()
    return DisagreementThread(monkeypatch, spec=spec, session=session)


async def test_the_build_mints_the_search_and_keeps_the_criterion_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _empty_thread(monkeypatch, _spec(_KINASES, pending(_WAITING)))

    await thread.build()

    [kinase_step] = [s for s in thread.graph.steps.values() if s.search_name]
    assert kinase_step.search_name == "GenesByText"
    assert [c.id for c in thread.spec.criteria] == [kinase_step.id, _WAITING]
    assert [c.id for c in thread.answered.criteria] == [kinase_step.id]


async def test_a_spec_that_only_waits_for_analyses_routes_to_the_eda_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _empty_thread(monkeypatch, _spec(pending(_WAITING)))

    with pytest.raises(ModelRetry) as excinfo:
        await thread.build()

    assert f'criterion_id="{_WAITING}"' in str(excinfo.value)
    assert thread.graph.steps == {}


async def test_a_frame_that_records_a_waiting_comparison_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The waiting criterion is the pass's work, not a pass that bound nothing."""
    thread = _empty_thread(monkeypatch, OperationalSpec(goal="24 h over 36 h"))
    thread.frames(lambda _found: _spec(pending(_WAITING)), declared=[])

    result = await thread.frame()

    assert isinstance(result, FrameResult)
    assert result.disposition == "spec_ready"
    assert [(c.id, c.needs_analysis_on) for c in thread.spec.criteria] == [
        (_WAITING, DATASET)
    ]
