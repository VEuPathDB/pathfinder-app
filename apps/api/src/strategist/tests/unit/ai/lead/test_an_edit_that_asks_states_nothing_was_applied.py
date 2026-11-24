from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import CombineOp, StrategyAst, flatten_tree

from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead import edit_dispatch, frame_dispatch, pre_turn
from strategist.ai.lead.deltas import EditDelta, FrameResult
from strategist.ai.lead.edit_dispatch import run_edit
from strategist.ai.lead.frame_dispatch import run_frame
from strategist.ai.lead.intent import IntentClassification, UserIntent
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
)
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.domain.strategy.spec_diff import CriterionChange, SpecDiff
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_RECORDED = json.loads(
    (
        Path(__file__).resolve().parents[3]
        / "fixtures"
        / "turns"
        / "sibling_strain_turn2_edit.json"
    ).read_text()
)
_RETURN = _RECORDED["editStrategyReturn"]
_DRAFT = _RETURN["summary"]
_REQUEST = _RECORDED["turn2Request"]
_NOTHING = "Nothing was applied: the strategy is unchanged."
_ME49 = "Toxoplasma gondii ME49"
_GT1 = "Toxoplasma gondii GT1"
_CLAIM = "criterion was changed"


def _leaf(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": node["id"],
        "searchName": node["searchName"],
        "parameters": {"organism": {"type": "string", "value": _ME49}},
    }


def _turn_one() -> StrategySession:
    nodes = _RECORDED["turn1Graph"]["nodes"]
    combine, pfam, expression = nodes
    tree = StrategyAst.model_validate(
        {
            "recordType": "transcript",
            "name": "kinases",
            "root": {
                "id": combine["id"],
                "operator": CombineOp.INTERSECT.value,
                "primaryInput": _leaf(pfam),
                "secondaryInput": _leaf(expression),
            },
        }
    )
    session = StrategySession(site_id="toxodb")
    graph = StrategyGraph(graph_id="g1", name="kinases", site_id="toxodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(tree.root)
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        step_counts={n["id"]: n["estimatedSize"] for n in nodes}
    )
    return session


def _moved_to_gt1(deps: Any) -> None:
    spec = deps.state.domain.operational_spec
    [pfam] = [c for c in spec.criteria if c.search_name == "GenesByInterproDomain"]
    pfam.resolved_params["organism"] = BoundValue(
        value=StringValue(value=_GT1), source="stated"
    )


async def _the_recorded_edit(monkeypatch: pytest.MonkeyPatch) -> EditDelta:
    state = pipeline_state("toxodb", user_prompt=_REQUEST, domain=StrategyDomainState())
    intent = UserIntent(
        classification=IntentClassification.EDIT_STRATEGY, inferred_goal=_REQUEST
    )
    deps = lead_deps(state, intent=intent, strategy_session=_turn_one())

    async def _frame(**kwargs: Any) -> FrameResult:
        _moved_to_gt1(kwargs["deps"])
        return FrameResult.model_validate(
            {
                "notes": _DRAFT,
                "disposition": "needs_user",
                "reported": _RETURN["reported"],
            }
        )

    async def _no_sheets(**_kwargs: Any) -> dict[str, Any]:
        return {}

    async def _no_marks(*_args: Any) -> dict[str, str]:
        return {}

    monkeypatch.setattr(edit_dispatch, "run_frame", _frame)
    monkeypatch.setattr(pre_turn, "sheet_params_for_searches", _no_sheets)
    monkeypatch.setattr(pre_turn, "organism_parameters", _no_marks)
    result = await run_edit(deps=deps, parent_tool_call_id="t2", reason=_REQUEST)
    assert isinstance(result, EditDelta)
    return result


def _strings(dumped: object) -> list[str]:
    match dumped:
        case str():
            return [dumped]
        case dict():
            return [s for v in dumped.values() for s in _strings(v)]
        case list():
            return [s for v in dumped for s in _strings(v)]
    return []


async def test_the_recorded_edit_states_nothing_was_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delta = await _the_recorded_edit(monkeypatch)

    dumped = delta.model_dump(by_alias=True, mode="json")
    assert dumped["summary"] == _NOTHING
    assert (dumped["operationsApplied"], dumped["pendingStepIds"]) == (
        0,
        ["step_69d06847"],
    )
    assert dumped["pendingPlan"]["rendered"].startswith(
        "Not applied, waiting on your answer: Changes: the Pfam protein-kinase "
        "criterion was changed"
    )
    assert [s for s in _strings(dumped) if _CLAIM in s] == [
        dumped["pendingPlan"]["text"],
        dumped["pendingPlan"]["rendered"],
    ]


async def test_a_needs_user_build_pass_carries_frames_text_only_as_a_pending_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _framed(**kwargs: Any) -> FrameResult:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        agent_deps.agent_state.operational_spec_draft.criteria.append(
            Criterion(id="c1", text="kinases", search_name="GenesByInterproDomain")
        )
        return FrameResult(disposition="needs_user", notes=_DRAFT)

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _framed)
    deps = lead_deps(pipeline_state("toxodb", user_prompt=_REQUEST))

    result = await run_frame(deps=deps, parent_tool_call_id="t1", work_order="frame")

    assert isinstance(result, FrameResult)
    dumped = result.model_dump(by_alias=True, mode="json")
    assert "summary" not in dumped
    assert [s for s in _strings(dumped) if _CLAIM in s] == [
        dumped["pendingPlan"]["text"],
        dumped["pendingPlan"]["rendered"],
    ]
    assert dumped["pendingPlan"]["rendered"].startswith("Not applied")


def test_a_route_is_said_beside_the_pending_plan() -> None:
    result = FrameResult(
        disposition="needs_user", notes=_DRAFT, route="Ask this on ToxoDB."
    )

    dumped = result.model_dump(by_alias=True, mode="json")
    assert (dumped["route"], dumped["pendingPlan"]["text"]) == (
        "Ask this on ToxoDB.",
        _DRAFT,
    )


def test_a_pass_with_no_text_carries_no_pending_plan() -> None:
    dumped = FrameResult(disposition="spec_ready").model_dump(by_alias=True)
    assert (dumped["pendingPlan"], dumped["route"]) == (None, "")


@pytest.mark.parametrize("disposition", ["needs_user", "unbound"])
def test_an_edit_that_applied_nothing_cannot_carry_an_applied_operation(
    disposition: str,
) -> None:
    with pytest.raises(ValidationError):
        EditDelta.model_validate(
            {"diff": SpecDiff(), "disposition": disposition, "operationsApplied": 1}
        )


@pytest.mark.parametrize("disposition", ["needs_user", "unbound"])
def test_an_edit_that_applied_nothing_cannot_carry_a_diff(disposition: str) -> None:
    changed = CriterionChange(criterion_id="step_69d06847", disposition="changed")

    with pytest.raises(ValidationError):
        EditDelta.model_validate(
            {"diff": SpecDiff(changes=[changed]), "disposition": disposition}
        )


def test_an_applied_edit_says_nothing_beside_its_diff() -> None:
    assert EditDelta(diff=SpecDiff(), operations_applied=1).summary == ""


def test_an_unbound_edit_states_nothing_was_applied_and_its_refusal() -> None:
    delta = EditDelta(diff=SpecDiff(), disposition="unbound", refusal="no organism")

    assert (delta.summary, delta.refusal) == (_NOTHING, "no organism")
