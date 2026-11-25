"""A patch writes only what moved: a new name never sends the search config.

The search config carries every stored parameter, so a PUT for a rename
writes the stored values over any value the researcher set on the site.
"""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import NumberValue, ParamValue
from veupathdb.domain.strategy import (
    CombineOp,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb_mcp.catalog import ValidatedParams

from strategist.domain.strategy.operations import (
    UpdateStepMetaOp,
    UpdateStepParamsOp,
)
from strategist.domain.strategy.session import StrategyGraph
from strategist.services.strategies import commit_tree
from strategist.services.strategies.commit import apply_and_commit
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.step_push_planner import (
    PatchAction,
    RecreateAction,
    SkipAction,
    StepPushPlan,
    plan_step_pushes,
)
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.record_classes import list_every_search_under
from strategist.tests._support.wdk_write_stubs import (
    held_as,
)
from strategist.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    install_stub_api,
    session_with,
)

_LEAF = "step_exportpred"
_WDK_LEAF = 440537303
_SCORE = "min_exportpred_score"


def _leaf(
    *,
    score: int = 10,
    name: str | None = "exported",
    weight: int | None = None,
) -> StrategyStepNode:
    params: dict[str, ParamValue] = {_SCORE: NumberValue(value=score)}
    return StrategyStepNode(
        id=_LEAF,
        search_name="GenesByExportPred",
        parameters=params,
        display_name=name,
        wdk_weight=weight,
    )


def _combine(*, name: str | None = None, weight: int | None = None) -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="step_join",
            search_name="__combine__",
            operator=CombineOp.INTERSECT,
            primary_input=StrategyStepNode(id="step_a", search_name="GenesByTaxon"),
            secondary_input=StrategyStepNode(id="step_b", search_name="GenesByTaxon"),
            display_name=name,
            wdk_weight=weight,
        ),
    )


def _plan_of(old: StrategyStepNode, new: StrategyStepNode) -> StepPushPlan:
    (entry,) = plan_step_pushes(
        old_ast=StrategyAst(record_type="transcript", root=old),
        new_ast=StrategyAst(record_type="transcript", root=new),
        existing_wdk_ids={_LEAF: _WDK_LEAF},
        held=held_as(StrategyAst(record_type="transcript", root=old)),
        unfinished=frozenset(),
    )
    return entry


class TestThePlanNamesWhatMoved:
    def test_a_new_name_is_a_name_write_alone(self) -> None:
        entry = _plan_of(_leaf(), _leaf(name="exported, renamed"))

        assert entry.action == PatchAction(search_config=False, name=True)

    def test_a_cleared_name_is_no_write(self) -> None:
        """WDK takes no empty name, so the site keeps the one it holds."""
        entry = _plan_of(_leaf(), _leaf(name=None))

        assert entry.action == SkipAction()

    def test_a_new_value_is_a_search_config_write_alone(self) -> None:
        entry = _plan_of(_leaf(), _leaf(score=12))

        assert entry.action == PatchAction(search_config=True, name=False)

    def test_a_new_value_and_a_new_name_write_both(self) -> None:
        entry = _plan_of(_leaf(), _leaf(score=12, name="exported, renamed"))

        assert entry.action == PatchAction(search_config=True, name=True)

    def test_a_new_weight_rides_the_search_config(self) -> None:
        entry = _plan_of(_leaf(), _leaf(weight=5))

        assert entry.action == PatchAction(search_config=True, name=False)

    def test_a_renamed_combine_writes_its_name(self) -> None:
        plan = plan_step_pushes(
            old_ast=_combine(name="A and B"),
            new_ast=_combine(name="A with B"),
            existing_wdk_ids={"step_a": 1, "step_b": 2, "step_join": 3},
            held=held_as(_combine(name="A and B")),
            unfinished=frozenset(),
        )

        assert {entry.step_id: entry.action for entry in plan}["step_join"] == (
            PatchAction(search_config=False, name=True)
        )

    def test_a_combine_takes_a_new_weight_at_creation(self) -> None:
        """WDK takes a combine's weight when it creates the combine."""
        plan = plan_step_pushes(
            old_ast=_combine(),
            new_ast=_combine(weight=5),
            existing_wdk_ids={"step_a": 1, "step_b": 2, "step_join": 3},
            held=held_as(_combine()),
            unfinished=frozenset(),
        )

        by_id = {entry.step_id: entry for entry in plan}
        assert (by_id["step_join"].action, by_id["step_join"].reason) == (
            RecreateAction(),
            "combine wdk_weight changed",
        )

    def test_a_transform_rewired_with_new_values_is_recreated(self) -> None:
        """A WDK transform keeps the input it was made with."""
        a = StrategyStepNode(id="step_a", search_name="GenesByTaxon")
        b = StrategyStepNode(id="step_b", search_name="GenesByTaxon")

        def ortholog(source: StrategyStepNode, score: int) -> StrategyAst:
            return StrategyAst(
                record_type="transcript",
                root=StrategyStepNode(
                    id="step_t",
                    search_name="GenesByOrthologs",
                    primary_input=source,
                    parameters={_SCORE: NumberValue(value=score)},
                ),
            )

        plan = plan_step_pushes(
            old_ast=ortholog(a, 10),
            new_ast=ortholog(b, 12),
            existing_wdk_ids={"step_a": 1, "step_b": 2, "step_t": 3},
            held=held_as(ortholog(a, 10)),
            unfinished=frozenset(),
        )

        by_id = {entry.step_id: entry for entry in plan}
        assert (by_id["step_t"].action, by_id["step_t"].reason) == (
            RecreateAction(),
            "transform input changed",
        )

    def test_a_patch_that_writes_nothing_is_refused(self) -> None:
        with pytest.raises(ValueError, match="writes nothing"):
            PatchAction(search_config=False, name=False)


def _graph(root: StrategyStepNode) -> StrategyGraph:
    graph = StrategyGraph("g1", "test", "plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    return graph


class TestTheCommitSendsWhatThePlanNames:
    @pytest.fixture
    def api(self, monkeypatch: pytest.MonkeyPatch) -> StubAPI:
        api = StubAPI()
        monkeypatch.setattr(commit_tree, "get_strategy_api", lambda _site: api)
        list_every_search_under(monkeypatch, "transcript")
        return api

    @pytest.fixture
    def validated(self, monkeypatch: pytest.MonkeyPatch) -> list[object]:
        """The parameters the commit validated."""
        seen: list[object] = []

        async def _record(*_args: Any, **kwargs: Any) -> ValidatedParams:
            seen.append(kwargs["stated"])
            return ValidatedParams(params=dict(kwargs["stated"]))

        monkeypatch.setattr(commit_tree, "validate_parameters", _record)
        return seen

    async def _commit(self, api: StubAPI, before: StrategyStepNode) -> None:
        graph = _graph(_leaf(score=12, name="exported, renamed"))
        sync_state = WDKSyncState(wdk_step_ids={_LEAF: _WDK_LEAF})
        api.holds(flatten_tree(before), sync_state)
        await commit_tree.commit_tree(
            site_id="plasmodb",
            steps=graph.steps,
            root_id=_LEAF,
            old=StrategyAst(record_type="transcript", root=before),
            sync_state=sync_state,
            target=commit_tree.CommitTarget(name="test", description=""),
        )

    async def test_a_rename_is_one_properties_patch(
        self, api: StubAPI, validated: list[object]
    ) -> None:
        await self._commit(api, _leaf(score=12))

        writes = api.step_writes()
        assert [call.name for call in writes] == ["update_step_properties"]
        assert writes[0].kwargs["spec"].custom_name == "exported, renamed"
        assert validated == []

    async def test_a_value_and_a_name_are_two_writes_in_order(
        self, api: StubAPI, validated: list[object]
    ) -> None:
        await self._commit(api, _leaf())

        assert [(c.name, c.kwargs["step_id"]) for c in api.step_writes()] == [
            ("update_step_search_config", _WDK_LEAF),
            ("update_step_properties", _WDK_LEAF),
        ]
        assert validated == [{_SCORE: NumberValue(value=12)}]


class TestACanvasRenameLeavesTheSitesValues:
    """The canvas commit is the path the graph route runs for a rename."""

    @pytest.fixture
    def api(self, monkeypatch: pytest.MonkeyPatch) -> StubAPI:
        return install_stub_api(monkeypatch)

    def _ctx(self) -> StrategyMutationContext:
        session = session_with(_leaf(), {_LEAF: _WDK_LEAF})
        return StrategyMutationContext(site_id="plasmodb", strategy_session=session)

    async def test_a_rename_sends_no_search_config(self, api: StubAPI) -> None:
        await apply_and_commit(
            deps=self._ctx(),
            op=UpdateStepMetaOp(step_id=_LEAF, display_name="exported, renamed"),
        )

        assert [
            call.name for call in api.calls if call.name.startswith("update_step")
        ] == ["update_step_properties"]

    async def test_a_value_edit_sends_the_search_config_and_no_name(
        self, api: StubAPI
    ) -> None:
        await apply_and_commit(
            deps=self._ctx(),
            op=UpdateStepParamsOp(
                step_id=_LEAF, parameters={_SCORE: NumberValue(value=12)}
            ),
        )

        writes = [c for c in api.calls if c.name.startswith("update_step")]
        assert [(c.name, c.kwargs.get("parameters")) for c in writes] == [
            ("update_step_search_config", {_SCORE: "12"})
        ]
