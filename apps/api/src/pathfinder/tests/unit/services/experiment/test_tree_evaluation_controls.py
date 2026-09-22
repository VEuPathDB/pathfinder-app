"""Tree evaluation reads one intersection payload through ``summarize_intersection``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, override

import pytest
from assistant_core.platform.types import JSONObject
from veupathdb.domain import WDKRecordIdPart
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.wdk import (
    CombinedStepSpec,
    NewStepSpec,
    StrategyAPI,
    VEuPathDBClient,
    WDKAnswer,
    WDKAnswerMeta,
    WDKFilterValue,
    WDKIdentifier,
    WDKRecordInstance,
    WDKStepTree,
)
from veupathdb_mcp.controls import ControlsContext

from pathfinder.services.experiment import tree_evaluation
from pathfinder.services.experiment.tree_evaluation import (
    _eval_control_set,
    run_controls_against_tree,
)


def _context(positive: list[str], negative: list[str]) -> ControlsContext:
    return ControlsContext(
        site_id="plasmodb",
        record_type="transcript",
        controls_search_name="GenesByGeneIds",
        controls_param_name="ds_gene_ids",
        controls_value_format="newline",
        positive_controls=positive,
        negative_controls=negative,
    )


def _tree() -> StrategyStepNode:
    return StrategyStepNode(id="s1", search_name="GenesByText")


def _payloads(monkeypatch: pytest.MonkeyPatch, by_label: dict[str, JSONObject]) -> None:
    async def _eval(
        _api: Any,
        _ctx: ControlsContext,
        _tree: StrategyStepNode,
        _control_ids: list[str],
        label: str,
    ) -> JSONObject:
        return by_label[label]

    monkeypatch.setattr(tree_evaluation, "_eval_control_set", _eval)
    monkeypatch.setattr(tree_evaluation, "get_strategy_api", lambda _site: object())


@pytest.mark.asyncio
async def test_recall_and_missing_read_the_identifiers_the_intersection_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _payloads(
        monkeypatch,
        {
            "positive": {
                "controlsCount": 3,
                "intersectionCount": 2,
                "intersectionIds": ["PF3D7_0100100", "PF3D7_0100200"],
                "targetEstimatedSize": 400,
            }
        },
    )

    result = await run_controls_against_tree(
        _context(["PF3D7_0100100", "PF3D7_0100200", "PF3D7_0100300"], []), _tree()
    )

    assert result.positive is not None
    assert result.positive.recall == pytest.approx(2 / 3)
    assert result.positive.missing_ids_sample == ["PF3D7_0100300"]
    assert result.target.estimated_size == 400


@pytest.mark.asyncio
async def test_the_negative_set_reports_the_hits_it_should_not_have(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _payloads(
        monkeypatch,
        {
            "negative": {
                "controlsCount": 2,
                "intersectionCount": 1,
                "intersectionIds": ["PF3D7_0200200"],
                "targetEstimatedSize": 400,
            }
        },
    )

    result = await run_controls_against_tree(
        _context([], ["PF3D7_0200100", "PF3D7_0200200"]), _tree()
    )

    assert result.negative is not None
    assert result.negative.false_positive_rate == pytest.approx(0.5)
    assert result.negative.unexpected_hits_sample == ["PF3D7_0200200"]


@pytest.mark.asyncio
async def test_a_payload_that_carries_no_identifiers_names_nothing_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _payloads(
        monkeypatch,
        {
            "positive": {"controlsCount": 2, "intersectionCount": 2},
            "negative": {"controlsCount": 2, "intersectionCount": 1},
        },
    )

    result = await run_controls_against_tree(
        _context(["PF3D7_0100100", "PF3D7_0100200"], ["a", "b"]), _tree()
    )

    assert result.positive is not None
    assert result.positive.missing_ids_sample == []
    assert result.positive.recall == pytest.approx(1.0)
    assert result.negative is not None
    assert result.negative.unexpected_hits_sample == []
    assert result.negative.false_positive_rate == pytest.approx(0.5)


class _EvalAPI(StrategyAPI):
    """Answers the WDK calls one control-set evaluation makes."""

    def __init__(self, found: list[str], counts: list[int]) -> None:
        super().__init__(VEuPathDBClient("https://plasmodb.example.org/plasmo"))
        self.pages_read: list[int] = []
        self.views: list[list[WDKFilterValue] | None] = []
        self._found = found
        self._counts = counts
        self._next = 100

    def _mint(self) -> WDKIdentifier:
        self._next += 1
        return WDKIdentifier(id=self._next)

    @override
    async def create_step(
        self, spec: NewStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        del spec, record_type, user_id
        return self._mint()

    @override
    async def create_combined_step(
        self, spec: CombinedStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        del spec, record_type, user_id
        return self._mint()

    @override
    async def create_strategy(
        self,
        step_tree: WDKStepTree,
        name: str,
        description: str | None = None,
        *,
        is_public: bool = False,
        is_saved: bool = False,
        is_internal: bool = False,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        del step_tree, name, description, is_public, is_saved, is_internal, user_id
        return self._mint()

    @override
    async def get_step_count(self, step_id: int, user_id: str | None = None) -> int:
        del step_id, user_id
        return self._counts.pop(0)

    @override
    async def get_step_answer(
        self,
        step_id: int,
        attributes: list[str] | None = None,
        pagination: dict[str, int] | None = None,
        *,
        view_filters: Sequence[WDKFilterValue] | None = None,
    ) -> WDKAnswer:
        del step_id, attributes
        if pagination is None:
            msg = "the evaluation reads one page at a time"
            raise AssertionError(msg)
        self.pages_read.append(pagination["numRecords"])
        self.views.append(None if view_filters is None else list(view_filters))
        return WDKAnswer(
            meta=WDKAnswerMeta(),
            records=[
                WDKRecordInstance(id=[WDKRecordIdPart(name="gene", value=gene)])
                for gene in self._found
            ],
        )


def _install(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _materialize(
        _api: Any, _node: StrategyStepNode, _record_type: str
    ) -> WDKStepTree:
        return WDKStepTree(step_id=11)

    async def _param_type(
        _api: Any, _record_type: str, _search: str, _param: str
    ) -> str:
        return "input-string"

    async def _delete(_api: Any, _strategy_id: int | None) -> None:
        return None

    monkeypatch.setattr(tree_evaluation, "_materialize_step_tree", _materialize)
    monkeypatch.setattr(tree_evaluation, "resolve_controls_param_type", _param_type)
    monkeypatch.setattr(tree_evaluation, "delete_temp_strategy", _delete)


@pytest.mark.asyncio
async def test_a_control_set_over_the_answer_limit_reads_no_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Past the limit the payload carries the count and no identifier list."""
    _install(monkeypatch)
    api = _EvalAPI(found=[], counts=[400, 3])
    controls = [f"PF3D7_{index:07d}" for index in range(501)]

    payload = await _eval_control_set(
        api, _context([], controls), _tree(), controls, "negative"
    )

    assert payload["intersectionIds"] is None
    assert payload["intersectionCount"] == 3
    assert payload["intersectionIdsSample"] == []
    assert api.pages_read == []


@pytest.mark.asyncio
async def test_a_control_set_under_the_answer_limit_reads_its_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch)
    api = _EvalAPI(found=["PF3D7_0200200"], counts=[400, 1])
    controls = ["PF3D7_0200100", "PF3D7_0200200"]

    payload = await _eval_control_set(
        api, _context([], controls), _tree(), controls, "negative"
    )

    assert payload["intersectionIds"] == ["PF3D7_0200200"]
    assert payload["intersectionCount"] == 1
    assert api.pages_read == [2]


@pytest.mark.asyncio
async def test_the_identifiers_of_a_transcript_tree_are_read_one_row_per_gene(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The page holds as many rows as controls, so each row must be a gene."""
    _install(monkeypatch)
    api = _EvalAPI(found=["PF3D7_0200200"], counts=[400, 1])
    controls = ["PF3D7_0200100", "PF3D7_0200200"]

    await _eval_control_set(api, _context([], controls), _tree(), controls, "negative")

    assert api.views == [
        [WDKFilterValue(name="representativeTranscriptOnly", value={})]
    ]
