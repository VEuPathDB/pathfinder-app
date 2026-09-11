"""The strategy-edit tools change one step and push that change to WDK."""

from __future__ import annotations

from typing import Any

import pytest
from assistant_core.platform.pydantic_base import CamelModel
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters.values import MultiPickValue, SinglePickValue
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.errors import ValidationError
from veupathdb_mcp import ToolErrorPayload

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone import strategy_edits
from pathfinder.ai.tools.standalone.strategy_edits import (
    delete_step,
    insert_saved_strategy,
    replace_subtree,
    update_combine_operator,
    update_leaf_params,
    update_step_metadata,
)
from pathfinder.domain.strategy.operations import DeleteResolution
from pathfinder.platform.errors import ErrorCode
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.tool_returns import returned

from ._strategy_edit_stubs import (
    StubAPI,
    combine,
    ctx,
    install_stub_api,
    leaf,
    seed,
    session_with,
)


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    return install_stub_api(monkeypatch)


class DeletedSteps(CamelModel):
    """The value ``delete_step`` returns."""

    ok: bool
    deleted: list[str]


class ReplacedSubtree(CamelModel):
    """The value ``replace_subtree`` returns."""

    ok: bool
    replaced_step_id: str
    dropped_step_ids: list[str]


class TestDeleteStep:
    async def test_deleting_an_input_collapses_its_combine(
        self, stub_api: StubAPI
    ) -> None:
        deps = seed(
            combine("C", leaf("A"), leaf("B")),
            wdk_step_ids={"A": 100, "B": 200, "C": 300},
        )

        payload = returned(await delete_step(ctx(deps), "A"), DeletedSteps)

        assert payload.ok is True
        assert sorted(payload.deleted) == ["A", "C"]
        assert stub_api.step_ids("delete_step") == {100, 300}

    @pytest.mark.usefixtures("stub_api")
    async def test_an_unknown_step_id_is_a_retry(self) -> None:
        deps = seed(leaf("A"), wdk_step_ids={"A": 100})
        with pytest.raises(ModelRetry):
            await delete_step(ctx(deps), "missing")

    async def test_promote_primary_keeps_the_primary_input(
        self, stub_api: StubAPI
    ) -> None:
        deps = seed(
            combine("c", leaf("a"), leaf("b")),
            wdk_step_ids={"a": 100, "b": 200, "c": 300},
        )

        payload = returned(
            await delete_step(
                ctx(deps), "c", resolution=DeleteResolution.PROMOTE_PRIMARY
            ),
            DeletedSteps,
        )

        assert sorted(payload.deleted) == ["b", "c"]
        assert stub_api.step_ids("delete_step") == {200, 300}


class TestUpdateLeafParams:
    async def test_the_new_values_reach_the_graph_and_wdk(
        self, stub_api: StubAPI
    ) -> None:
        deps = seed(
            leaf("a", params={"organism": MultiPickValue(values=["Pf3D7"])}),
            wdk_step_ids={"a": 100},
        )

        await update_leaf_params(
            ctx(deps), "a", {"organism": MultiPickValue(values=["Pf3D7", "Pf7G8"])}
        )

        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps["a"].parameters == {
            "organism": MultiPickValue(values=["Pf3D7", "Pf7G8"]),
        }
        patches = stub_api.named("update_step_search_config")
        assert [call.kwargs["step_id"] for call in patches] == [100]

    @pytest.mark.usefixtures("stub_api")
    async def test_validation_sees_the_merged_config_not_the_one_change(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        deps = seed(
            leaf(
                "a",
                params={
                    "organism": MultiPickValue(values=["Pf3D7"]),
                    "ReadFrequencyPercent": SinglePickValue(value="60%"),
                },
            ),
            wdk_step_ids={"a": 100},
        )
        seen: dict[str, dict[str, Any]] = {}

        async def _capture_validate(
            _search_ctx: Any, *, parameters: dict[str, Any], **_kw: Any
        ) -> dict[str, Any]:
            seen["parameters"] = dict(parameters)
            return dict(parameters)

        monkeypatch.setattr(strategy_edits, "validate_parameters", _capture_validate)

        await update_leaf_params(
            ctx(deps), "a", {"ReadFrequencyPercent": SinglePickValue(value="80%")}
        )

        assert set(seen["parameters"]) == {"organism", "ReadFrequencyPercent"}
        assert seen["parameters"]["ReadFrequencyPercent"] == SinglePickValue(
            value="80%"
        )
        assert seen["parameters"]["organism"] == MultiPickValue(values=["Pf3D7"])

    @pytest.mark.usefixtures("stub_api")
    async def test_a_combine_step_has_no_leaf_params(self) -> None:
        deps = seed(
            combine("c", leaf("a"), leaf("b")),
            wdk_step_ids={"a": 100, "b": 200, "c": 300},
        )
        with pytest.raises(ModelRetry):
            await update_leaf_params(ctx(deps), "c", {})

    @pytest.mark.usefixtures("stub_api")
    async def test_a_rejected_value_retries_with_the_valid_options(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        deps = seed(
            leaf("a", params={"organism": MultiPickValue(values=["Pf3D7"])}),
            wdk_step_ids={"a": 100},
        )

        async def _raising_validate(*_args: Any, **_kwargs: Any) -> dict[str, object]:
            raise ValidationError(
                title="Invalid parameter value",
                detail="Parameter 'organism' does not accept 'NotARealOrganism'.",
                errors=[
                    {
                        "param": "organism",
                        "value": "NotARealOrganism",
                        "validOptions": ["Pf3D7", "PvP01"],
                    },
                ],
            )

        monkeypatch.setattr(strategy_edits, "validate_parameters", _raising_validate)

        with pytest.raises(ModelRetry) as excinfo:
            await update_leaf_params(
                ctx(deps),
                "a",
                {"organism": MultiPickValue(values=["NotARealOrganism"])},
            )

        msg = str(excinfo.value)
        assert "Invalid parameter value" in msg
        assert "validOptions" in msg
        assert "NotARealOrganism" in msg


class TestUpdateCombineOperator:
    @pytest.mark.usefixtures("stub_api")
    async def test_the_operator_changes_on_the_combine(self) -> None:
        deps = seed(
            combine("c", leaf("a"), leaf("b"), op=CombineOp.INTERSECT),
            wdk_step_ids={"a": 100, "b": 200, "c": 300},
        )

        await update_combine_operator(ctx(deps), "c", CombineOp.UNION)

        assert deps.strategy_session.graph is not None
        assert deps.strategy_session.graph.steps["c"].operator == CombineOp.UNION

    @pytest.mark.usefixtures("stub_api")
    async def test_a_leaf_has_no_operator(self) -> None:
        deps = seed(leaf("a"), wdk_step_ids={"a": 100})
        with pytest.raises(ModelRetry):
            await update_combine_operator(ctx(deps), "a", CombineOp.INTERSECT)

    @pytest.mark.usefixtures("stub_api")
    async def test_colocate_without_its_params_is_a_retry(self) -> None:
        deps = seed(
            combine("c", leaf("a"), leaf("b")),
            wdk_step_ids={"a": 100, "b": 200, "c": 300},
        )
        with pytest.raises(ModelRetry):
            await update_combine_operator(
                ctx(deps), "c", CombineOp.COLOCATE, colocation_params=None
            )


class TestUpdateStepMetadata:
    async def test_a_rename_keeps_the_step(self, stub_api: StubAPI) -> None:
        deps = seed(leaf("a"), wdk_step_ids={"a": 100})

        await update_step_metadata(ctx(deps), "a", "renamed")

        assert deps.strategy_session.graph is not None
        assert deps.strategy_session.graph.steps["a"].display_name == "renamed"
        assert stub_api.named("delete_step") == []


class TestReplaceSubtree:
    async def test_the_old_subtree_goes_and_the_new_one_is_created(
        self, stub_api: StubAPI
    ) -> None:
        deps = seed(
            combine("c", leaf("a"), leaf("b")),
            wdk_step_ids={"a": 100, "b": 200, "c": 300},
        )

        payload = returned(
            await replace_subtree(ctx(deps), "a", leaf("new_a")), ReplacedSubtree
        )

        assert payload.replaced_step_id == "a"
        assert "a" in payload.dropped_step_ids
        assert 100 in stub_api.step_ids("delete_step")
        created = stub_api.named("create_step")
        assert any(call.kwargs["search_name"] == "GenesByTaxon" for call in created)

    @pytest.mark.usefixtures("stub_api")
    async def test_an_unknown_step_id_is_a_retry(self) -> None:
        deps = seed(leaf("a"), wdk_step_ids={"a": 100})
        with pytest.raises(ModelRetry):
            await replace_subtree(ctx(deps), "missing", leaf("new"))


class TestInsertSavedStrategy:
    @pytest.mark.usefixtures("stub_api")
    async def test_it_needs_a_persistent_conversation(self) -> None:
        session = session_with(leaf("a"), wdk_step_ids={"a": 100})
        session.sync_state = WDKSyncState(wdk_step_ids={"a": 100})
        deps = AgentDeps(
            site_id="plasmodb",
            strategy_session=session,
            conversation_id=None,
            db_session_factory=None,
        )

        res = returned(
            await insert_saved_strategy(ctx(deps), "a", 12345), ToolErrorPayload
        )

        assert res.ok is False
        assert res.code == ErrorCode.INTERNAL_ERROR.value
