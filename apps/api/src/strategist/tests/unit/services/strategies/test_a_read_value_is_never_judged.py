"""A value read from WDK is never judged, so it never refuses a sibling edit or a push."""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import (
    MultiPickValue,
    NumberValue,
    ParamValue,
    StringValue,
)
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, flatten_tree
from veupathdb.errors import ValidationError
from veupathdb.wdk import WDKSearchConfig
from veupathdb_mcp.catalog import ValidatedParams

from strategist.domain.strategy.operations import UpdateStepParamsOp
from strategist.domain.strategy.operations.apply import apply_operation
from strategist.domain.strategy.session import StrategyGraph
from strategist.domain.strategy.spec_edit_guard import StatedCriterion
from strategist.services.strategies import commit_tree, stated_sides
from strategist.services.strategies.stated_sides import canonical_batch
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.record_classes import list_every_search_under
from strategist.tests._support.wdk_write_stubs import skip_the_tree_put

_PATTERN = "profile_pattern"
_READ: dict[str, ParamValue] = {
    _PATTERN: StringValue(value="%zzzz:Y%"),
    "organism": MultiPickValue(values=["A strain the site retired"]),
}


class _Catalog:
    """Judges only what it is asked to state: a retired code and a lost term refuse."""

    def __init__(self) -> None:
        self.stated: list[set[str]] = []

    async def __call__(self, *_args: Any, **kwargs: Any) -> ValidatedParams:
        stated: dict[str, ParamValue] = dict(kwargs["stated"])
        self.stated.append(set(stated))
        if any(stated.get(name) == value for name, value in _READ.items()):
            raise ValidationError(title="Invalid parameter value", detail="retired")
        return ValidatedParams(params=stated, record_class="transcript")


def _values(weight: float) -> dict[str, ParamValue]:
    return {**_READ, "max_weight": NumberValue(value=weight)}


def _ast(weight: float) -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="s", search_name="GenesByOrthologPattern", parameters=_values(weight)
        ),
    )


async def _commit(graph: StrategyGraph, before: StrategyAst) -> None:
    await commit_tree.commit_tree(
        site_id="plasmodb",
        steps=graph.steps,
        root_id="s",
        old=before,
        sync_state=WDKSyncState(wdk_step_ids={"s": 9}),
        target=commit_tree.CommitTarget(name="g", description=""),
    )


class _Api:
    def __init__(self) -> None:
        self.written: list[dict[str, str]] = []

    async def update_step_search_config(
        self,
        step_id: int,
        search_config: WDKSearchConfig,
        record_type: str,
        search_name: str,
    ) -> None:
        del step_id, record_type, search_name
        self.written.append(dict(search_config.parameters))


async def test_a_sibling_edit_and_its_push_never_judge_a_read_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog, api = _Catalog(), _Api()

    async def _listed(_site: str, names: list[str]) -> dict[str, str]:
        return dict.fromkeys(names, "transcript")

    monkeypatch.setattr(stated_sides, "validate_parameters", catalog)
    monkeypatch.setattr(stated_sides, "search_record_types", _listed)
    monkeypatch.setattr(commit_tree, "validate_parameters", catalog)
    monkeypatch.setattr(commit_tree, "get_strategy_api", lambda _site: api)
    skip_the_tree_put(monkeypatch)
    list_every_search_under(monkeypatch, "transcript")
    graph = StrategyGraph("g", "g", "plasmodb")
    graph.steps = flatten_tree(_ast(50).root)
    graph.steps["s"].record_class = "transcript"
    graph.recompute_roots()
    edit = UpdateStepParamsOp(
        step_id="s", parameters={"max_weight": NumberValue(value=60)}
    )

    batch = await canonical_batch(
        graph=graph, stated={}, site_id="plasmodb", ops=[edit]
    )
    for op in batch.ops:
        apply_operation(graph, op)
    await _commit(graph, _ast(50))

    assert catalog.stated == [{"max_weight"}, {"max_weight"}]
    assert graph.steps["s"].parameters == _values(60)
    assert api.written == [
        {
            "profile_pattern": "%zzzz:Y%",
            "organism": '["A strain the site retired"]',
            "max_weight": "60",
        }
    ]


async def test_restating_a_held_pattern_with_a_retired_code_pushes_the_new_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog, api = _Catalog(), _Api()

    async def _listed(_site: str, names: list[str]) -> dict[str, str]:
        return dict.fromkeys(names, "transcript")

    monkeypatch.setattr(stated_sides, "validate_parameters", catalog)
    monkeypatch.setattr(stated_sides, "search_record_types", _listed)
    monkeypatch.setattr(commit_tree, "validate_parameters", catalog)
    monkeypatch.setattr(commit_tree, "get_strategy_api", lambda _site: api)
    skip_the_tree_put(monkeypatch)
    list_every_search_under(monkeypatch, "transcript")
    graph = StrategyGraph("g", "g", "plasmodb")
    graph.steps = flatten_tree(_ast(50).root)
    graph.steps["s"].record_class = "transcript"
    graph.recompute_roots()
    restated = StringValue(value="%pfal:Y%")
    spec = {"s": StatedCriterion(text="in P. falciparum", values={_PATTERN: restated})}
    edit = UpdateStepParamsOp(step_id="s", parameters={_PATTERN: restated})

    batch = await canonical_batch(
        graph=graph, stated=spec, site_id="plasmodb", ops=[edit]
    )
    for op in batch.ops:
        apply_operation(graph, op)
    await _commit(graph, _ast(50))

    assert graph.steps["s"].parameters[_PATTERN] == restated
    assert [w[_PATTERN] for w in api.written] == ["%pfal:Y%"]
