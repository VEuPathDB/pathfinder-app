"""The groups of a computed comparison become a criterion on the site's group id
list search: uploaded to the researcher's account, named by the question and
described as a snapshot, and refused when the step does not hold the list."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import TypeAdapter
from pydantic_ai import ModelRetry, RunContext, ToolFailed
from veupathdb.domain.parameters import InputDatasetValue
from veupathdb_mcp.catalog import PhyleticPattern

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.tools.standalone._frame_result import SetCriterionResult
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.spec_tree import build_step_tree
from pathfinder.services.strategies.dataset_sources import dataset_source
from pathfinder.tests._support.computed_comparison import GROUP_IDS, held_comparison
from pathfinder.tests._support.group_list_site import (
    DATASET,
    STRATEGY,
    served_group_list,
)
from pathfinder.tests._support.tool_returns import returned

from .conftest import agent_run_context

_SITE = "orthomcl"
_QUESTION = "groups with more proteins per genome in Toxoplasma than Plasmodium"
_PATTERN: PhyleticPattern = TypeAdapter(PhyleticPattern).validate_python(
    {
        "kind": "compare",
        "left": {"kind": "codes", "codes": ["TOXO"]},
        "right": {"kind": "codes", "codes": ["PLAS"]},
        "reading": "averages",
        "condition": "more_than",
    }
)
_HELD = held_comparison(_PATTERN, date(2026, 10, 25))


def _asked(ctx: RunContext[AgentDeps]) -> RunContext[AgentDeps]:
    ctx.deps.intent = IntentClassification.NEW_STRATEGY
    return ctx


def _state() -> AgentToolState:
    return AgentToolState(computed_comparisons={_HELD.handle: _HELD})


async def test_the_groups_are_uploaded_bound_and_leave_no_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state()

    with served_group_list(monkeypatch, counted=3) as site:
        result = returned(
            await set_criterion(
                _asked(agent_run_context(site_id=_SITE, agent_state=state)),
                criterion_id="c_more_in_toxo",
                text=_QUESTION,
                role="seed",
                computed_groups=_HELD.handle,
            ),
            SetCriterionResult,
        )

    name = f"{_QUESTION} (computed snapshot, 2026-10-25)"
    description = (
        "A computed snapshot of OrthoMCL's data on 2026-10-25: the 3 groups the "
        "comparison selected, uploaded as a list. The ids are fixed; a later "
        "release maps each id to the groups it became, so the count can change."
    )
    assert (site.uploaded, site.deleted) == ([list(GROUP_IDS)], [STRATEGY])
    assert [(s["searchName"], s["searchConfig"]) for s in site.steps] == [
        ("GroupsByNameList", {"parameters": {"group_names": str(DATASET)}})
    ]
    [criterion] = state.operational_spec_draft.criteria
    assert (criterion.search_name, criterion.record_class) == (
        "GroupsByNameList",
        "group",
    )
    assert (criterion.search_display_name, criterion.result_count) == (name, 3)
    assert criterion.resolved_params == {
        "group_names": BoundValue(
            value=InputDatasetValue(dataset_id=str(DATASET)),
            source="chosen",
            basis=description,
            label="the 3 groups of the comparison",
        )
    }
    assert criterion.param_display_names == {"group_names": "Groups"}
    assert result.computed_groups is not None
    assert (result.computed_groups.step_name, result.result_count) == (name, 3)
    assert state.computed_comparisons[_HELD.handle].dataset_id == str(DATASET)


async def test_the_build_leaf_runs_the_list_search_on_the_saved_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state()
    with served_group_list(monkeypatch, counted=3):
        await set_criterion(
            _asked(agent_run_context(site_id=_SITE, agent_state=state)),
            criterion_id="c_more_in_toxo",
            text=_QUESTION,
            role="seed",
            computed_groups=_HELD.handle,
        )
    spec = state.operational_spec_draft.model_copy(
        update={
            "structure": SpecStructure(
                root=StructureNode(kind="leaf", criterion_id="c_more_in_toxo")
            )
        }
    )

    leaf = build_step_tree(spec).root
    dataset = InputDatasetValue(dataset_id=str(DATASET))
    assert (leaf.search_name, leaf.parameters) == (
        "GroupsByNameList",
        {"group_names": dataset},
    )
    assert dataset_source("group_names", dataset) is None


async def test_a_step_that_does_not_hold_the_list_fails_with_no_rebuild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state()

    with (
        served_group_list(monkeypatch, counted=2) as site,
        pytest.raises(ToolFailed) as refused,
    ):
        await set_criterion(
            _asked(agent_run_context(site_id=_SITE, agent_state=state)),
            criterion_id="c_more_in_toxo",
            text=_QUESTION,
            role="seed",
            computed_groups=_HELD.handle,
        )

    assert str(refused.value) == (
        "set_criterion cannot hold the computed groups as a list step: 3 ids were "
        "uploaded to GroupsByNameList and its step holds 2 records, so the step is "
        "not the list. An id the site does not hold adds no record, and an id of an "
        "earlier release adds each current record it maps to. Nothing was recorded "
        "and no step was saved. The counted answer stands: state its counts, and do "
        "not build the comparison again to save it."
    )
    assert (site.deleted, state.operational_spec_draft.criteria) == ([STRATEGY], [])


async def test_a_handle_no_comparison_holds_is_sent_back() -> None:
    state = AgentToolState()

    with pytest.raises(ModelRetry) as refused:
        await set_criterion(
            _asked(agent_run_context(site_id=_SITE, agent_state=state)),
            criterion_id="c_more_in_toxo",
            text=_QUESTION,
            role="seed",
            computed_groups="groups:000000000000",
        )

    assert str(refused.value).startswith(
        "computed_groups names groups:000000000000, and no computed comparison"
    )
    assert state.operational_spec_draft.criteria == []


async def test_a_comparison_of_no_group_saves_nothing() -> None:
    empty = _HELD.model_copy(
        update={
            "answer": _HELD.answer.model_copy(
                update={
                    "groups": 0,
                    "group_ids": (),
                    "both_held": 0,
                    "left_only": 0,
                    "right_only": 0,
                }
            )
        }
    )
    state = AgentToolState(computed_comparisons={empty.handle: empty})

    with pytest.raises(ModelRetry) as refused:
        await set_criterion(
            _asked(agent_run_context(site_id=_SITE, agent_state=state)),
            criterion_id="c_more_in_toxo",
            text=_QUESTION,
            role="seed",
            computed_groups=empty.handle,
        )

    assert str(refused.value) == (
        f"The computed comparison {empty.handle} selects no group, so there is no "
        "list to save; nothing was recorded."
    )
    assert state.operational_spec_draft.criteria == []
