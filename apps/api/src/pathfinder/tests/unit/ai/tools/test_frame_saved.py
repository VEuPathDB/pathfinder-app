"""FRAME can list the user's saved strategies and start a criterion from one."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic_ai import ModelRetry

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.agents.strategy_instructions import pinned_frame_workspace
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone import _frame_saved
from pathfinder.ai.tools.standalone.frame_spec import drop_criterion, set_criterion
from pathfinder.ai.tools.standalone.saved_strategies import list_saved_strategies
from pathfinder.ai.tools.toolsets._dynamic import ValidatingEnumToolset
from pathfinder.ai.tools.toolsets.frame import build_toolset
from pathfinder.domain.strategy.ast import COMBINE_SEARCH_NAME, StrategyStepNode
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.ops import CombineOp
from pathfinder.services.strategies.insert_saved import ClonedSavedStrategy
from pathfinder.services.strategies.saved_library import SavedStrategyListing

_CONVERSATION_ID = "9bd3a584-0000-4000-8000-000000000001"
_SAVED_NAME = "Pf protease union (text OR GO)"
_SAVED_WDK_ID = 330534203


def _listing() -> list[SavedStrategyListing]:
    return [
        SavedStrategyListing(
            conversation_id=_CONVERSATION_ID,
            name=_SAVED_NAME,
            wdk_strategy_id=_SAVED_WDK_ID,
            record_type="transcript",
            root_count=227,
            step_count=3,
        )
    ]


def _cloned() -> ClonedSavedStrategy:
    return ClonedSavedStrategy(
        root=StrategyStepNode(
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.UNION,
            primary_input=StrategyStepNode(search_name="GenesByText"),
            secondary_input=StrategyStepNode(search_name="GenesByGoTerm"),
        ),
        name=_SAVED_NAME,
        record_type="transcript",
        wdk_strategy_id=_SAVED_WDK_ID,
    )


def _ctx(state: AgentToolState) -> MagicMock:
    ctx = MagicMock()
    ctx.tool_call_id = "call_1"
    ctx.deps.agent_state = state
    ctx.deps.site_id = "plasmodb"
    ctx.deps.user_id = uuid4()
    ctx.deps.db_session_factory = MagicMock()
    return ctx


def _serve_library(
    monkeypatch: pytest.MonkeyPatch,
    entries: list[SavedStrategyListing],
) -> None:
    async def _list(*_args: object, **_kwargs: object) -> list[SavedStrategyListing]:
        return entries

    async def _clone(*_args: object, **_kwargs: object) -> ClonedSavedStrategy:
        return _cloned()

    monkeypatch.setattr(_frame_saved, "list_saved_strategies", _list)
    monkeypatch.setattr(_frame_saved, "clone_saved_strategy", _clone)


class TestTheFrameToolsetOffersTheLibrary:
    def test_list_saved_strategies_is_registered(self) -> None:
        toolset = build_toolset()
        assert "list_saved_strategies" in set(toolset.wrapped.tools)

    @pytest.mark.asyncio
    async def test_the_listing_reports_name_id_count_and_steps(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve_library(monkeypatch, _listing())
        result = (await list_saved_strategies(_ctx(AgentToolState()))).return_value
        assert len(result.saved_strategies) == 1
        entry = result.saved_strategies[0]
        assert entry.name == _SAVED_NAME
        assert entry.conversation_id == _CONVERSATION_ID
        assert entry.wdk_strategy_id == _SAVED_WDK_ID
        assert entry.root_count == 227
        assert entry.step_count == 3


class TestACriterionStartsFromASavedStrategy:
    @pytest.mark.asyncio
    async def test_the_criterion_carries_the_reference_and_no_search(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve_library(monkeypatch, _listing())
        state = AgentToolState()
        result = (
            await set_criterion(
                _ctx(state),
                criterion_id="c_saved",
                text=f"start from my saved strategy {_SAVED_NAME!r}",
                role="seed",
                saved_strategy=_SAVED_NAME,
            )
        ).return_value
        assert result.saved_strategy is not None
        assert result.saved_strategy.wdk_strategy_id == _SAVED_WDK_ID
        criterion = state.operational_spec_draft.criteria[0]
        assert criterion.search_name == ""
        assert criterion.bound is True
        assert criterion.saved_strategy_ref is not None
        assert criterion.saved_strategy_ref.name == _SAVED_NAME
        assert criterion.saved_strategy_ref.root_count == 227
        assert criterion.saved_strategy_ref.subtree.operator == CombineOp.UNION

    @pytest.mark.asyncio
    async def test_the_wdk_id_resolves_the_same_saved_strategy(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve_library(monkeypatch, _listing())
        state = AgentToolState()
        await set_criterion(
            _ctx(state),
            criterion_id="c_saved",
            text="the union I saved",
            role="seed",
            saved_strategy=str(_SAVED_WDK_ID),
        )
        criterion = state.operational_spec_draft.criteria[0]
        assert criterion.saved_strategy_ref is not None
        assert criterion.saved_strategy_ref.name == _SAVED_NAME

    @pytest.mark.asyncio
    async def test_a_call_with_neither_a_search_nor_a_saved_strategy_retries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve_library(monkeypatch, _listing())
        with pytest.raises(ModelRetry, match="saved_strategy"):
            await set_criterion(
                _ctx(AgentToolState()),
                criterion_id="c1",
                text="something",
            )


class TestAnUnknownReferenceStopsTheBuild:
    @pytest.mark.asyncio
    async def test_it_retries_naming_the_listing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve_library(monkeypatch, _listing())
        with pytest.raises(ModelRetry, match=re.escape(_SAVED_NAME)):
            await set_criterion(
                _ctx(AgentToolState()),
                criterion_id="c_saved",
                text="start from my saved strategy 'Nope'",
                role="seed",
                saved_strategy="Nope",
            )

    @pytest.mark.asyncio
    async def test_it_leaves_the_criterion_open_so_the_frame_needs_the_user(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve_library(monkeypatch, _listing())
        state = AgentToolState()
        with pytest.raises(ModelRetry):
            await set_criterion(
                _ctx(state),
                criterion_id="c_saved",
                text="start from my saved strategy 'Nope'",
                role="seed",
                saved_strategy="Nope",
            )
        criterion = state.operational_spec_draft.criteria[0]
        assert criterion.bound is False
        assert [slot.param_name for slot in criterion.open_params] == ["saved_strategy"]
        assert criterion.open_params[0].options == [_SAVED_NAME]
        assert state.operational_spec_draft.ready_to_build is False

    @pytest.mark.asyncio
    async def test_an_empty_library_says_so(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve_library(monkeypatch, [])
        with pytest.raises(ModelRetry, match="no saved strategies"):
            await set_criterion(
                _ctx(AgentToolState()),
                criterion_id="c_saved",
                text="start from my saved strategy 'Nope'",
                role="seed",
                saved_strategy="Nope",
            )

    @pytest.mark.asyncio
    async def test_the_open_criterion_cannot_be_dropped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve_library(monkeypatch, _listing())
        state = AgentToolState()
        with pytest.raises(ModelRetry):
            await set_criterion(
                _ctx(state),
                criterion_id="c_saved",
                text="start from my saved strategy 'Nope'",
                role="seed",
                saved_strategy="Nope",
            )
        with pytest.raises(ModelRetry, match="Ask the user which one"):
            drop_criterion(
                _ctx(state), criterion_id="c_saved", reason="cannot resolve it"
            )
        assert len(state.operational_spec_draft.criteria) == 1

    def test_a_criterion_without_a_saved_slot_still_drops(self) -> None:
        state = AgentToolState()
        state.frame_set_criterion(Criterion(id="c1", text="t", search_name="S1"))
        result = drop_criterion(
            _ctx(state), criterion_id="c1", reason="no realizable search"
        ).return_value
        assert result.criterion_id == "c1"
        assert state.operational_spec_draft.criteria == []


class TestTheEnumGuardLeavesTheSavedPathAlone:
    @pytest.mark.asyncio
    async def test_an_empty_search_name_reaches_the_tool(self) -> None:
        wrapped = MagicMock()
        wrapped.call_tool = AsyncMock(return_value="called")
        guarded: ValidatingEnumToolset[AgentDeps] = ValidatingEnumToolset(
            wrapped=wrapped,
            build_overrides=lambda _ctx: {
                ("set_criterion", "search_name"): ["GenesWithSignalPeptide"]
            },
        )
        args = {
            "criterion_id": "c_saved",
            "search_name": "",
            "saved_strategy": _SAVED_NAME,
        }
        assert (
            await guarded.call_tool("set_criterion", args, MagicMock(), MagicMock())
            == "called"
        )

    @pytest.mark.asyncio
    async def test_an_unknown_search_name_is_still_refused(self) -> None:
        wrapped = MagicMock()
        wrapped.call_tool = AsyncMock(return_value="called")
        guarded: ValidatingEnumToolset[AgentDeps] = ValidatingEnumToolset(
            wrapped=wrapped,
            build_overrides=lambda _ctx: {
                ("set_criterion", "search_name"): ["GenesWithSignalPeptide"]
            },
        )
        with pytest.raises(ModelRetry, match="GenesWithSignalPeptide"):
            await guarded.call_tool(
                "set_criterion",
                {"criterion_id": "c1", "search_name": "GenesByInvention"},
                MagicMock(),
                MagicMock(),
            )


class TestTheWorkspaceNamesTheSavedStrategy:
    @pytest.mark.asyncio
    async def test_a_saved_criterion_is_not_shown_as_unbound(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve_library(monkeypatch, _listing())
        state = AgentToolState()
        ctx = _ctx(state)
        await set_criterion(
            ctx,
            criterion_id="c_saved",
            text="start from the union I saved",
            role="seed",
            saved_strategy=_SAVED_NAME,
        )
        workspace = pinned_frame_workspace(ctx)
        assert workspace is not None
        assert _SAVED_NAME in workspace
        assert "227 results, 3 steps" in workspace
        assert "UNBOUND" not in workspace
