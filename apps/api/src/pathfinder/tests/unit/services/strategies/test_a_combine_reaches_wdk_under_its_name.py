"""WDK holds a combine under its operator's name, never its question name.

WDK names a step it receives without a name after its search, so a combine
pushed with no name reads as the boolean question on the site.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import (
    CombineOp,
    StrategyAst,
    StrategyStep,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.domain.strategy.operations import UpdateStepParamsOp
from pathfinder.services.strategies import step_wdk_push
from pathfinder.services.strategies.commit import apply_and_commit
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.step_push_planner import (
    PatchAction,
    plan_step_pushes,
)
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    combine,
    install_stub_api,
    leaf,
    session_with,
)

_WDK_DEFAULT = "boolean_question_TranscriptRecordClasses_TranscriptRecordClass"
_WDK_IDS = {"step_a": 440537303, "step_b": 440537313, "step_join": 440537323}


def _join(name: str | None, search_name: str = "__combine__") -> StrategyStep:
    node = StrategyStepNode(
        id="step_join",
        search_name=search_name,
        display_name=name,
        operator=CombineOp.UNION,
        primary_input=leaf("step_a"),
        secondary_input=leaf("step_b"),
    )
    return flatten_tree(node)["step_join"]


class TestTheCreateSendsTheName:
    @pytest.fixture
    def api(self, monkeypatch: pytest.MonkeyPatch) -> StubAPI:
        api = StubAPI()
        monkeypatch.setattr(step_wdk_push, "get_strategy_api", lambda _site: api)
        return api

    async def _pushed_name(self, api: StubAPI, step: StrategyStep) -> object:
        await step_wdk_push.push_step_to_wdk(
            sync_state=WDKSyncState(wdk_step_ids=dict(_WDK_IDS)),
            step=step,
            site_id="plasmodb",
            record_type="transcript",
            search_name="__combine__",
            parameters={},
        )
        (call,) = api.named("create_combined_step")
        return call.kwargs["custom_name"]

    @pytest.mark.parametrize(
        ("name", "search_name"),
        [
            (None, "__combine__"),
            (_WDK_DEFAULT, _WDK_DEFAULT),
            ("INTERSECT combine", "__combine__"),
        ],
    )
    async def test_an_unnamed_combine_goes_under_its_operators_name(
        self, api: StubAPI, name: str | None, search_name: str
    ) -> None:
        assert await self._pushed_name(api, _join(name, search_name)) == "Union"

    async def test_a_researchers_name_goes_as_given(self, api: StubAPI) -> None:
        pushed = await self._pushed_name(api, _join("Exported or secreted"))

        assert pushed == "Exported or secreted"


def test_a_pushed_combine_whose_name_lags_plans_a_name_patch() -> None:
    def ast(name: str | None) -> StrategyAst:
        root = combine("step_join", leaf("step_a"), leaf("step_b"))
        return StrategyAst(
            record_type="transcript",
            root=root.model_copy(update={"display_name": name}),
        )

    plan = plan_step_pushes(
        old_ast=ast(None), new_ast=ast("Intersect"), existing_wdk_ids=_WDK_IDS
    )

    assert {entry.step_id: entry.action for entry in plan}["step_join"] == (
        PatchAction(search_config=False, name=True)
    )


async def test_an_edit_names_a_combine_pushed_without_a_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = install_stub_api(monkeypatch)
    session = session_with(
        combine("step_join", leaf("step_a"), leaf("step_b")), _WDK_IDS
    )

    await apply_and_commit(
        deps=StrategyMutationContext(site_id="plasmodb", strategy_session=session),
        op=UpdateStepParamsOp(
            step_id="step_a", parameters={"min_score": NumberValue(value=3)}
        ),
    )

    named = {
        call.kwargs["step_id"]: call.kwargs["spec"].custom_name
        for call in api.named("update_step_properties")
    }
    assert named == {_WDK_IDS["step_join"]: "Intersect"}
    assert session.graph is not None
    assert session.graph.steps["step_join"].display_name == "Intersect"
