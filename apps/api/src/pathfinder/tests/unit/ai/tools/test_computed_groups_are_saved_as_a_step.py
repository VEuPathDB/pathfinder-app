"""The groups of a computed comparison become a criterion on the site's group id
list search: uploaded to the researcher's account, named by the question and
described as a snapshot, and refused when the step does not hold the list."""

from __future__ import annotations

import itertools
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date

import httpx
import pytest
import respx
from pydantic import TypeAdapter
from pydantic_ai import ModelRetry
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.parameters import InputDatasetValue
from veupathdb.wdk import get_site
from veupathdb_mcp.catalog import PhyleticPattern, get_discovery_service

from pathfinder.ai.agents.state import AgentToolState
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
from pathfinder.tests._support.tool_returns import returned

from .conftest import agent_run_context

_SITE = "orthomcl"
_ACCOUNTS = itertools.count()
_USER = 376
_DATASET = 9001
_STEP = 501
_STRATEGY = 77
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


class _Catalog:
    def find_record_type_for_search(self, search_name: str) -> str | None:
        return "group" if search_name == "GroupsByNameList" else None


@dataclass
class _GroupListSite:
    counted: int
    uploaded: list[list[str]] = field(default_factory=list)
    steps: list[dict[str, object]] = field(default_factory=list)
    deleted: list[int] = field(default_factory=list)

    async def dataset(self, request: httpx.Request) -> httpx.Response:
        self.uploaded.append(json.loads(request.content)["sourceContent"]["ids"])
        return httpx.Response(200, json={"id": _DATASET})

    async def step(self, request: httpx.Request) -> httpx.Response:
        self.steps.append(json.loads(request.content))
        return httpx.Response(200, json={"id": _STEP})

    async def count(self, request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "meta": {"totalCount": self.counted, "responseCount": 0},
                "records": [],
            },
        )

    async def found(self, request: httpx.Request) -> httpx.Response:
        del request
        sent = self.steps[-1]
        return httpx.Response(
            200,
            json={
                "id": _STEP,
                "searchName": sent["searchName"],
                "searchConfig": sent["searchConfig"],
                "recordClassName": "group",
                "estimatedSize": self.counted,
                "strategyId": _STRATEGY,
            },
        )

    async def removed(self, request: httpx.Request) -> httpx.Response:
        del request
        self.deleted.append(_STRATEGY)
        return httpx.Response(204)


async def _catalog(site_id: str) -> _Catalog:
    assert site_id == _SITE
    return _Catalog()


@contextmanager
def _served(monkeypatch: pytest.MonkeyPatch, counted: int) -> Iterator[_GroupListSite]:
    monkeypatch.setattr(get_discovery_service(), "get_catalog", _catalog)
    site = _GroupListSite(counted=counted)
    service = get_site(_SITE).service_url
    users = f"{service}/users/{_USER}"
    token = veupathdb_auth_token_ctx.set(f"a-registered-token-{next(_ACCOUNTS)}")
    try:
        with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
            router.get(f"{get_site(_SITE).web_base_url}/app").mock(
                return_value=httpx.Response(200)
            )
            router.get(f"{service}/users/current").mock(
                return_value=httpx.Response(200, json={"id": _USER, "isGuest": False})
            )
            router.get(f"{service}/record-types/group/searches/GroupsByNameList").mock(
                return_value=httpx.Response(404, text="not recorded")
            )
            router.post(f"{users}/datasets").mock(side_effect=site.dataset)
            router.post(f"{users}/steps").mock(side_effect=site.step)
            router.post(f"{users}/strategies").mock(
                return_value=httpx.Response(200, json={"id": _STRATEGY})
            )
            router.post(f"{users}/steps/{_STEP}/reports/standard").mock(
                side_effect=site.count
            )
            router.get(f"{users}/steps/{_STEP}").mock(side_effect=site.found)
            router.delete(f"{users}/strategies/{_STRATEGY}").mock(
                side_effect=site.removed
            )
            yield site
    finally:
        veupathdb_auth_token_ctx.reset(token)


def _state() -> AgentToolState:
    return AgentToolState(computed_comparisons={_HELD.handle: _HELD})


async def test_the_groups_are_uploaded_and_bound_as_a_named_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state()

    with _served(monkeypatch, counted=3) as site:
        result = returned(
            await set_criterion(
                agent_run_context(site_id=_SITE, agent_state=state),
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
        "comparison selected, uploaded as a list. The site does not re-run the "
        "comparison, so a later release of its data does not change this step."
    )
    assert site.uploaded == [list(GROUP_IDS)]
    assert [(s["searchName"], s["searchConfig"]) for s in site.steps] == [
        ("GroupsByNameList", {"parameters": {"group_names": str(_DATASET)}})
    ]
    [criterion] = state.operational_spec_draft.criteria
    assert (criterion.search_name, criterion.record_class) == (
        "GroupsByNameList",
        "group",
    )
    assert (criterion.search_display_name, criterion.result_count) == (name, 3)
    assert criterion.resolved_params == {
        "group_names": BoundValue(
            value=InputDatasetValue(dataset_id=str(_DATASET)),
            source="chosen",
            basis=description,
            label="the 3 groups of the comparison",
        )
    }
    assert criterion.param_display_names == {"group_names": "Groups"}
    assert result.computed_groups is not None
    assert (result.computed_groups.step_name, result.result_count) == (name, 3)
    assert state.computed_comparisons[_HELD.handle].dataset_id == str(_DATASET)


async def test_the_build_leaf_runs_the_list_search_on_the_saved_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state()
    with _served(monkeypatch, counted=3):
        await set_criterion(
            agent_run_context(site_id=_SITE, agent_state=state),
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
    dataset = InputDatasetValue(dataset_id=str(_DATASET))
    assert (leaf.search_name, leaf.parameters) == (
        "GroupsByNameList",
        {"group_names": dataset},
    )
    assert dataset_source("group_names", dataset) is None


async def test_a_step_that_does_not_hold_the_list_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state()

    with (
        _served(monkeypatch, counted=2) as site,
        pytest.raises(ModelRetry) as refused,
    ):
        await set_criterion(
            agent_run_context(site_id=_SITE, agent_state=state),
            criterion_id="c_more_in_toxo",
            text=_QUESTION,
            role="seed",
            computed_groups=_HELD.handle,
        )

    assert str(refused.value) == (
        "3 ids were uploaded to GroupsByNameList and its step holds 2 records, so "
        "the step is not the list. An id the site does not hold adds no record, and "
        "an id of an earlier release adds each current record it maps to. The "
        "computed groups were not saved and nothing was recorded. Build the "
        "comparison again and save the new answer."
    )
    assert (site.deleted, state.operational_spec_draft.criteria) == ([_STRATEGY], [])


async def test_a_handle_no_comparison_holds_is_sent_back() -> None:
    state = AgentToolState()

    with pytest.raises(ModelRetry) as refused:
        await set_criterion(
            agent_run_context(site_id=_SITE, agent_state=state),
            criterion_id="c_more_in_toxo",
            text=_QUESTION,
            role="seed",
            computed_groups="groups:000000000000",
        )

    assert str(refused.value).startswith(
        "computed_groups names groups:000000000000, and no computed comparison"
    )
    assert state.operational_spec_draft.criteria == []
