"""An edit turn declares what happened to every criterion it started with.

The claim that the rest was preserved is a comparison the dispatch runs before
it accepts FRAME's result.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import MultiPickValue, NumberValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.spec_diff import CriterionChange
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_PROMPT = "use the DeRisi dataset for the expression filter, keep the rest"


def _text_criterion() -> Criterion:
    return Criterion(
        id="step_text",
        text="genes matching protease",
        search_name="GenesByText",
    )


def _go_criterion(organism: str = "Plasmodium") -> Criterion:
    return Criterion(
        id="step_go",
        text="genes annotated with protein kinase activity",
        search_name="GenesByGoTerm",
        resolved_params={"organism": MultiPickValue(values=[organism])},
    )


def _expression_criterion(percentile: float = 80) -> Criterion:
    return Criterion(
        id="step_expr",
        text="genes in the top expression decile",
        search_name="GenesByRNASeqEvidence",
        resolved_params={"min_expression_percentile": NumberValue(value=percentile)},
    )


def _spec(*criteria: Criterion) -> OperationalSpec:
    return OperationalSpec(
        goal="find kinases",
        criteria=list(criteria),
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id=c.id) for c in criteria
                ],
            )
        ),
    )


def _three() -> OperationalSpec:
    return _spec(_text_criterion(), _go_criterion(), _expression_criterion())


def _kept(*criterion_ids: str) -> list[CriterionChange]:
    return [
        CriterionChange(criterion_id=cid, disposition="kept") for cid in criterion_ids
    ]


def _deps(before: OperationalSpec) -> LeadDeps:
    return lead_deps(
        pipeline_state(
            user_prompt=_PROMPT,
            domain=StrategyDomainState(
                operational_spec=before.model_copy(deep=True),
                spec_before_turn=before.model_copy(deep=True),
            ),
        ),
    )


def _stub_frame(
    monkeypatch: pytest.MonkeyPatch,
    after: OperationalSpec,
    changes: list[CriterionChange],
) -> None:
    """Drive one FRAME dispatch that leaves ``after`` in the shared draft."""

    async def _fake(**kwargs: Any) -> FrameResult:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        agent_deps.agent_state.operational_spec_draft = after.model_copy(deep=True)
        return FrameResult(disposition="spec_ready", summary="edited", changes=changes)

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)


async def _edit(deps: LeadDeps, order: str = "edit") -> FrameResult | Any:
    return await run_frame(
        deps=deps,
        parent_tool_call_id="t1",
        work_order=frame_work_order(order, deps.state),
    )


async def test_undeclared_drop_is_a_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_frame(
        monkeypatch,
        _spec(_text_criterion(), _go_criterion()),
        _kept("step_text", "step_go"),
    )

    with pytest.raises(ModelRetry) as excinfo:
        await _edit(_deps(_three()))

    assert "step_expr" in str(excinfo.value)


async def test_declared_drop_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_frame(
        monkeypatch,
        _spec(_text_criterion(), _go_criterion()),
        [
            *_kept("step_text", "step_go"),
            CriterionChange(
                criterion_id="step_expr",
                disposition="dropped",
                reason="the user asked for it to go",
            ),
        ],
    )

    result = await _edit(_deps(_three()))

    assert isinstance(result, FrameResult)
    assert result.disposition == "spec_ready"


async def test_kept_criterion_keeps_its_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_frame(
        monkeypatch,
        _spec(
            _text_criterion(),
            _go_criterion(organism="Plasmodium falciparum 3D7"),
            _expression_criterion(),
        ),
        _kept("step_text", "step_go", "step_expr"),
    )

    with pytest.raises(ModelRetry) as excinfo:
        await _edit(_deps(_three()))

    message = str(excinfo.value)
    assert "step_go" in message
    assert "Plasmodium falciparum 3D7" in message


async def test_a_declared_change_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_frame(
        monkeypatch,
        _spec(_text_criterion(), _go_criterion(), _expression_criterion(90)),
        [
            *_kept("step_text", "step_go"),
            CriterionChange(
                criterion_id="step_expr",
                disposition="changed",
                changed_params={"min_expression_percentile": "90"},
            ),
        ],
    )

    result = await _edit(_deps(_three()))

    assert isinstance(result, FrameResult)
    assert result.disposition == "spec_ready"


async def test_a_fresh_build_declares_nothing_and_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No spec before the turn means there is nothing to preserve."""
    _stub_frame(monkeypatch, _spec(_text_criterion()), [])
    deps = _deps(_three())
    deps.state.domain.spec_before_turn = None

    result = await _edit(deps, order="build")

    assert isinstance(result, FrameResult)
    assert result.disposition == "spec_ready"


async def test_an_undeclared_criterion_beside_a_declared_change_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three criteria in, two out, nothing declared dropped: a retry."""
    _stub_frame(
        monkeypatch,
        _spec(_text_criterion(), _expression_criterion(90)),
        [
            CriterionChange(
                criterion_id="step_expr",
                disposition="changed",
                changed_params={"min_expression_percentile": "90"},
            )
        ],
    )

    with pytest.raises(ModelRetry) as excinfo:
        await _edit(_deps(_three()))

    message = str(excinfo.value)
    assert "step_go" in message
    assert "protein kinase activity" in message


async def test_a_refused_edit_leaves_the_spec_as_the_turn_found_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The retry's workspace must still show the criterion it has to preserve."""
    _stub_frame(
        monkeypatch,
        _spec(_text_criterion(), _go_criterion()),
        _kept("step_text"),
    )
    deps = _deps(_three())

    with pytest.raises(ModelRetry):
        await _edit(deps)

    spec = deps.state.domain.operational_spec
    assert spec is not None
    assert {c.id for c in spec.criteria} == {"step_text", "step_go", "step_expr"}
