"""An edit that adds a transform the site lists for its input's record type is
the edit the message asks for, whatever its words."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import added_criteria, frame_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_dispatch import run_frame
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.listed_transforms import listed_transform_ids
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.record_class_check import SearchRecordClasses
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
)

_GROUPS = Criterion(
    id="step_groups",
    text="groups held by every lantern",
    search_name="GroupsByLanternPattern",
    record_class="lantern_group",
)
_MEMBERS = Criterion(
    id="c_members",
    text="the members of those groups",
    search_name="LanternsFromGroups",
    record_class="lantern",
)
_TRANSFORMS = {
    "LanternsFromGroups": SearchRecordClasses(
        display_name="Lanterns from groups", returns="lantern", takes=("lantern_group",)
    ),
    "GroupsFromLanterns": SearchRecordClasses(
        display_name="Groups from lanterns", returns="lantern_group", takes=("lantern",)
    ),
}


def _transformed(added: Criterion) -> OperationalSpec:
    return OperationalSpec(
        goal="lantern groups",
        criteria=[_GROUPS, added],
        structure=SpecStructure(
            root=StructureNode.model_validate(
                {
                    "kind": "transform",
                    "criterionId": added.id,
                    "inputs": [{"kind": "leaf", "criterionId": _GROUPS.id}],
                }
            )
        ),
    )


def test_a_transform_listed_for_its_input_class_is_named() -> None:
    assert listed_transform_ids(_transformed(_MEMBERS), _TRANSFORMS) == {"c_members"}


def test_a_transform_that_takes_another_class_is_not_named() -> None:
    back = Criterion(
        id="c_back",
        text="groups of those",
        search_name="GroupsFromLanterns",
        record_class="lantern_group",
    )

    assert listed_transform_ids(_transformed(back), _TRANSFORMS) == frozenset()


def test_a_search_the_site_lists_as_no_transform_is_not_named() -> None:
    assert listed_transform_ids(_transformed(_MEMBERS), {}) == frozenset()


def _edit(monkeypatch: pytest.MonkeyPatch, added: Criterion) -> LeadDeps:
    async def _fake(**kwargs: Any) -> FrameResult:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        agent_deps.agent_state.operational_spec_draft = _transformed(added)
        return FrameResult(disposition="spec_ready", summary="carried")

    async def _listed(site_id: str) -> dict[str, SearchRecordClasses]:
        return _TRANSFORMS

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _fake)
    monkeypatch.setattr(added_criteria, "site_transforms", _listed)
    deps = lead_deps(
        pipeline_state("orthomcl", user_prompt="Now show me what is inside them."),
        intent=UserIntent(
            classification=IntentClassification.EXTEND_STRATEGY,
            inferred_goal="The members of the groups.",
        ),
        strategy_session=session_with_one_step("orthomcl"),
    )
    deps.state.domain.operational_spec = OperationalSpec(
        goal="lantern groups", criteria=[_GROUPS]
    )
    return deps


async def test_an_edit_adding_a_listed_transform_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _edit(monkeypatch, _MEMBERS)

    result = await run_frame(deps=deps, parent_tool_call_id="t1", work_order="edit")

    assert isinstance(result, FrameResult)
    assert result.summary == "carried"


async def test_an_edit_adding_an_unlisted_transform_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    back = Criterion(
        id="c_back",
        text="groups of those",
        search_name="GroupsFromLanterns",
        record_class="lantern_group",
    )
    deps = _edit(monkeypatch, back)

    with pytest.raises(ModelRetry) as refused:
        await run_frame(deps=deps, parent_tool_call_id="t1", work_order="edit")

    assert str(refused.value).startswith("The pass adds 'c_back' ('groups of those')")
