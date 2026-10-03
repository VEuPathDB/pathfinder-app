"""What a framing pass did to each criterion it found is read from the wire
values of the two specs: a criterion is kept only when no value moved."""

from __future__ import annotations

from typing import Any

import pytest
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
    DroppedCriterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.spec_diff import CriterionChange
from pathfinder.tests._support.bound_values import bound
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
        resolved_params=bound({"organism": MultiPickValue(values=[organism])}),
    )


def _expression_criterion(percentile: float = 80) -> Criterion:
    return Criterion(
        id="step_expr",
        text="genes in the top expression decile",
        search_name="GenesByRNASeqEvidence",
        resolved_params=bound(
            {"min_expression_percentile": NumberValue(value=percentile)}
        ),
    )


def _spec(*criteria: Criterion) -> OperationalSpec:
    return OperationalSpec(
        goal="find kinases",
        criteria=list(criteria),
        structure=SpecStructure(root=_intersect_of(criteria)),
    )


def _intersect_of(criteria: tuple[Criterion, ...]) -> StructureNode:
    """One criterion is its leaf; more are an INTERSECT of their leaves."""
    leaves = [StructureNode(kind="leaf", criterion_id=c.id) for c in criteria]
    if len(leaves) == 1:
        return leaves[0]
    return StructureNode(kind="combine", operator=CombineOp.INTERSECT, inputs=leaves)


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
        work_order=frame_work_order(order, deps),
    )


async def _dispositions(
    monkeypatch: pytest.MonkeyPatch,
    after: OperationalSpec,
    claimed: list[CriterionChange],
) -> list[tuple[str, str, str]]:
    _stub_frame(monkeypatch, after, claimed)
    result = await _edit(_deps(_three()))
    assert isinstance(result, FrameResult)
    return [(c.criterion_id, c.disposition, c.reason) for c in result.changes]


async def test_a_criterion_whose_value_moved_is_never_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pass calls every criterion kept; the GO organism moved."""
    after = _spec(
        _text_criterion(),
        _go_criterion(organism="Plasmodium falciparum 3D7"),
        _expression_criterion(),
    )

    found = await _dispositions(
        monkeypatch, after, _kept("step_text", "step_go", "step_expr")
    )

    assert found == [
        ("step_text", "kept", ""),
        ("step_go", "changed", ""),
        ("step_expr", "kept", ""),
    ]


async def test_a_criterion_the_pass_calls_changed_is_kept_when_nothing_moved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claimed = [
        CriterionChange(
            criterion_id="step_expr",
            disposition="changed",
            changed_params={"min_expression_percentile": "90"},
        )
    ]

    found = await _dispositions(monkeypatch, _three(), claimed)

    assert [disposition for _, disposition, _ in found] == ["kept", "kept", "kept"]


async def test_a_dropped_criterion_carries_the_reason_the_pass_gave(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    after = _spec(_text_criterion(), _go_criterion())
    after.dropped = [
        DroppedCriterion(
            text=_expression_criterion().text, reason="the user asked for it to go"
        )
    ]

    found = await _dispositions(monkeypatch, after, [])

    assert found[2] == ("step_expr", "dropped", "the user asked for it to go")


async def test_a_fresh_build_derives_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """No spec before the turn means no criterion was found."""
    _stub_frame(monkeypatch, _spec(_text_criterion()), _kept("step_text"))
    deps = _deps(_three())
    deps.state.domain.operational_spec = None
    deps.state.domain.spec_before_turn = None

    result = await _edit(deps, order="build")

    assert isinstance(result, FrameResult)
    assert (result.disposition, result.changes) == ("spec_ready", [])
