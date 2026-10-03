"""An edit over a held strategy adds no criterion the message does not state:
a question is answered with a comparison, not with a step."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_dispatch import run_frame
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
    session_with_one_step,
)

_UNDO = (
    "Please undo those changes: search the exact phrase in the product field "
    "only and drop the domain steps. Then answer my question about the other "
    "two genes."
)
_PRODUCT_STEP = Criterion(
    id="step_c4026561",
    text="exact phrase polar tube protein in the product field",
    search_name="GenesByText",
)
_ALL_FIELDS = Criterion(
    id="c_all_text_comparison",
    text=(
        "Broader all-text search for the exact phrase polar tube protein in "
        "Enterocytozoon bieneusi H348, to identify genes beyond the "
        "product-only result"
    ),
    search_name="GenesByText",
)


def _adds(monkeypatch: pytest.MonkeyPatch, added: Criterion) -> FrameResult:
    delta = FrameResult(disposition="spec_ready", summary="added one")

    async def _fake(**kwargs: Any) -> FrameResult:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        agent_deps.agent_state.operational_spec_draft.criteria.append(added)
        return delta

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)
    return delta


def _edit_deps(
    message: str, stated: list[str], asks: list[str], *, held: bool
) -> LeadDeps:
    deps = lead_deps(
        pipeline_state("microsporidiadb", user_prompt=message),
        intent=UserIntent(
            classification=IntentClassification.EDIT_STRATEGY,
            inferred_goal="Keep the product-field search.",
            asks=asks,
            explicit_constraints=[
                requirement(ConstraintKind.OTHER, value, value) for value in stated
            ],
        ),
        strategy_session=session_with_one_step("microsporidiadb") if held else None,
    )
    deps.state.domain.operational_spec = OperationalSpec(
        goal="polar tube protein genes", criteria=[_PRODUCT_STEP]
    )
    return deps


_UNDO_STATED = [
    "search the exact phrase in the product field only",
    "drop the domain steps",
]
_UNDO_ASKS = ["answer my question about the other two genes"]


async def test_an_edit_that_adds_a_criterion_no_requirement_states_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _adds(monkeypatch, _ALL_FIELDS)
    deps = _edit_deps(_UNDO, _UNDO_STATED, _UNDO_ASKS, held=True)

    with pytest.raises(ModelRetry) as refused:
        await run_frame(deps=deps, parent_tool_call_id="t1", work_order="edit it")

    assert str(refused.value) == (
        "The pass adds 'c_all_text_comparison' ('Broader all-text search for the "
        "exact phrase polar tube protein in Enterocytozoon bieneusi H348, to "
        "identify genes beyond the product-only result'), which no requirement "
        "of the message states; a question is answered with "
        "compare_search_variants, not with a step. Drop it, or name the "
        "requirement the message states for it."
    )
    spec = deps.state.domain.operational_spec
    assert spec is not None
    assert [c.id for c in spec.criteria] == ["step_c4026561"]


async def test_an_edit_that_adds_a_stated_criterion_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    added = Criterion(
        id="c_chr3", text="genes on chromosome 3", search_name="GenesByLocation"
    )
    delta = _adds(monkeypatch, added)
    deps = _edit_deps("Also limit it to chromosome 3.", ["chromosome 3"], [], held=True)

    result = await run_frame(deps=deps, parent_tool_call_id="t1", work_order="edit")

    assert isinstance(result, FrameResult)
    assert (result.disposition, result.summary) == (delta.disposition, delta.summary)


async def test_a_new_build_adds_criteria_unchecked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delta = _adds(monkeypatch, _ALL_FIELDS)
    deps = _edit_deps(_UNDO, _UNDO_STATED, _UNDO_ASKS, held=False)

    result = await run_frame(deps=deps, parent_tool_call_id="t1", work_order="frame")

    assert isinstance(result, FrameResult)
    assert (result.disposition, result.summary) == (delta.disposition, delta.summary)
