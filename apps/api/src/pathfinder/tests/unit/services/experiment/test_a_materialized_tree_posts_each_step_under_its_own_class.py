from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

import pytest
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    ColocationParams,
    CombineOp,
    StrategyStepNode,
)
from veupathdb.errors import ValidationError, WDKError
from veupathdb.wdk import NewStepSpec, WDKIdentifier

from pathfinder.services.eval import build_gold_strategy
from pathfinder.services.experiment import materialization
from pathfinder.services.experiment.materialization import materialize_step_tree
from pathfinder.services.strategies import record_classes
from pathfinder.tests._support.orthomcl_record_classes import (
    serve_orthomcl_record_classes,
)
from pathfinder.tests._support.record_classes import list_each_search_under
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import StubAPI

_LISTED = {
    "GroupsByPhyleticPattern": "group",
    "SnpsByLocation": "snp",
    "GenesBySpanLogic": "transcript",
}
_MIXED = (
    "The INTERSECT of step_protein (Proteins) and step_mammals (Ortholog Groups) "
    "joins two record types."
)


def _serve(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    api = StubAPI()
    monkeypatch.setattr(materialization, "get_strategy_api", lambda _site: api)
    return api


def _join(
    left: StrategyStepNode, right: StrategyStepNode, op: CombineOp = CombineOp.INTERSECT
) -> StrategyStepNode:
    return StrategyStepNode(
        id="step_join",
        search_name=COMBINE_SEARCH_NAME,
        operator=op,
        colocation_params=ColocationParams() if op is CombineOp.COLOCATE else None,
        primary_input=left,
        secondary_input=right,
    )


def _protein() -> StrategyStepNode:
    return StrategyStepNode(id="step_protein", search_name="ByIdList")


def _mammals() -> StrategyStepNode:
    return StrategyStepNode(id="step_mammals", search_name="GroupsByPhyleticPattern")


async def test_a_tree_of_two_record_types_is_refused_before_any_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_orthomcl_record_classes(monkeypatch)
    api = _serve(monkeypatch)
    made: list[int] = []

    with pytest.raises(ValidationError) as refused:
        await materialize_step_tree("orthomcl", _join(_protein(), _mammals()), made)

    assert (api.calls, made) == ([], [])
    assert refused.value.detail is not None
    assert refused.value.detail.startswith(_MIXED)


async def test_a_group_tree_posts_each_step_under_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_orthomcl_record_classes(monkeypatch)
    api = _serve(monkeypatch)
    groups = StrategyStepNode(
        id="step_groups", search_name="GroupsFromSequences", primary_input=_protein()
    )
    made: list[int] = []

    await materialize_step_tree("orthomcl", _join(groups, _mammals()), made)

    assert [(c.name, c.kwargs["record_type"]) for c in api.calls] == [
        ("create_step", "sequence"),
        ("create_transform_step", "group"),
        ("create_step", "group"),
        ("create_combined_step", "group"),
    ]
    assert made == [9001, 9002, 9003, 9004]


async def test_a_colocation_posts_its_own_search_under_its_listed_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    list_each_search_under(monkeypatch, _LISTED)
    api = _serve(monkeypatch)
    near = _join(
        StrategyStepNode(id="step_groups", search_name="GroupsByPhyleticPattern"),
        StrategyStepNode(id="step_snps", search_name="SnpsByLocation"),
        CombineOp.COLOCATE,
    )

    await materialize_step_tree("plasmodb", near, [])

    assert [
        (c.name, c.kwargs.get("search_name"), c.kwargs["record_type"])
        for c in api.calls
    ] == [
        ("create_step", "GroupsByPhyleticPattern", "group"),
        ("create_step", "SnpsByLocation", "snp"),
        ("create_transform_step", "GenesBySpanLogic", "transcript"),
    ]


async def test_a_gold_tree_of_two_record_types_posts_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_orthomcl_record_classes(monkeypatch)
    api = _serve(monkeypatch)
    monkeypatch.setattr("pathfinder.services.eval.get_strategy_api", lambda _s: api)
    tree: dict[str, Any] = _join(_protein(), _mammals()).model_dump(
        by_alias=True, exclude_none=True, mode="json"
    )

    with pytest.raises(ValidationError):
        await build_gold_strategy(
            gold_id="gold-mixed", site_id="orthomcl", step_tree=tree
        )

    assert api.calls == []


_STRATEGY_REFUSED = WDKError("strategy refused", status=500)


class _GoldAPI(StubAPI):
    datasets: list[list[str]]
    released: list[list[int]]
    posted: list[dict[str, str]]

    def __init__(self) -> None:
        super().__init__()
        self.datasets = []
        self.released = []
        self.posted = []

    async def create_step(
        self, spec: NewStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        self.posted.append(dict(spec.search_config.parameters))
        return await super().create_step(spec, record_type, user_id)

    async def create_dataset(self, config: Any) -> int:
        self.datasets.append(list(config.source_content.ids))
        return 7001

    async def create_strategy(self, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise _STRATEGY_REFUSED

    async def delete_orphaned_steps(self, step_ids: list[int]) -> list[int]:
        self.released.append(list(step_ids))
        return []


def _serve_gold(monkeypatch: pytest.MonkeyPatch) -> _GoldAPI:
    api = _GoldAPI()
    monkeypatch.setattr(materialization, "get_strategy_api", lambda _site: api)
    monkeypatch.setattr("pathfinder.services.eval.get_strategy_api", lambda _s: api)
    return api


async def test_a_gold_tree_the_site_cannot_run_provisions_no_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_orthomcl_record_classes(monkeypatch)
    api = _serve_gold(monkeypatch)
    tree = _join(_protein(), _mammals()).model_dump(
        by_alias=True, exclude_none=True, mode="json"
    )

    with pytest.raises(ValidationError):
        await build_gold_strategy(
            gold_id="gold-mixed",
            site_id="orthomcl",
            step_tree=tree,
            dataset_gene_ids={"ds_gene_ids": ["PF3D7_1133400"]},
        )

    assert (api.datasets, api.calls) == ([], [])


async def test_a_gold_strategy_the_site_refuses_releases_its_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_orthomcl_record_classes(monkeypatch)
    api = _serve_gold(monkeypatch)
    tree = _join(_protein(), StrategyStepNode(id="step_more", search_name="ByIdList"))

    with pytest.raises(WDKError):
        await build_gold_strategy(
            gold_id="gold-proteins",
            site_id="orthomcl",
            step_tree=tree.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )

    assert api.released == [[9001, 9002, 9003]]


async def test_a_gold_build_checks_its_tree_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_orthomcl_record_classes(monkeypatch)
    api = _serve_gold(monkeypatch)
    checked: list[str] = []
    refusal = record_classes.tree_record_class_refusal

    async def _counted(
        site_id: str, root: StrategyStepNode, held: Mapping[str, str]
    ) -> str | None:
        checked.append(root.id)
        return await refusal(site_id, root, held)

    monkeypatch.setattr(materialization, "tree_record_class_refusal", _counted)
    tree = _join(_protein(), StrategyStepNode(id="step_more", search_name="ByIdList"))

    with pytest.raises(WDKError):
        await build_gold_strategy(
            gold_id="gold-proteins",
            site_id="orthomcl",
            step_tree=tree.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )

    assert (checked, api.released) == (["step_join"], [[9001, 9002, 9003]])


_RECORDED_SHAPE: dict[str, Any] = {
    "searchName": "boolean_question_SequenceRecordClasses_SequenceRecordClass",
    "parameters": {},
    "displayName": "Combine Protein results",
    "operator": "INTERSECT",
    "primaryInput": {
        "searchName": "ByIdList",
        "parameters": {
            "ds_gene_ids": {"type": "input-dataset", "datasetId": "1"},
        },
        "displayName": "Protein IDs",
    },
    "secondaryInput": {
        "searchName": "ByIdList",
        "parameters": {},
        "displayName": "More protein IDs",
    },
}


async def test_a_gold_tree_whose_steps_carry_no_id_posts_every_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_orthomcl_record_classes(monkeypatch)
    api = _serve_gold(monkeypatch)

    with pytest.raises(WDKError):
        await build_gold_strategy(
            gold_id="gold-recorded",
            site_id="orthomcl",
            step_tree=copy.deepcopy(_RECORDED_SHAPE),
            dataset_gene_ids={"ds_gene_ids": ["PF3D7_1133400"]},
        )

    assert api.datasets == [["PF3D7_1133400"]]
    assert api.posted[0]["ds_gene_ids"] == "7001"
    assert api.released == [[9001, 9002, 9003]]


async def test_a_gold_tree_with_no_dataset_and_no_ids_posts_every_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_orthomcl_record_classes(monkeypatch)
    api = _serve_gold(monkeypatch)
    tree = copy.deepcopy(_RECORDED_SHAPE)
    tree["primaryInput"]["parameters"] = {}

    with pytest.raises(WDKError):
        await build_gold_strategy(
            gold_id="gold-recorded", site_id="orthomcl", step_tree=tree
        )

    assert api.released == [[9001, 9002, 9003]]
