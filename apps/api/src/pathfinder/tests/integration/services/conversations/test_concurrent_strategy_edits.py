"""Two overlapping edits on one thread must both reach the persisted AST."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.domain.parameters.values import MultiPickValue, ParamValue, StringValue
from pathfinder.domain.strategy.ast import StrategyStepNode
from pathfinder.domain.strategy.operations import (
    UpdateCombineOperatorOp,
    UpdateStepParamsOp,
)
from pathfinder.domain.strategy.ops import CombineOp
from pathfinder.domain.strategy.strategy_ast import StrategyAst
from pathfinder.domain.strategy.tree import walk
from pathfinder.integrations.veupathdb.wdk_models import (
    CombinedStepSpec,
    NewStepSpec,
    PatchStepSpec,
    WDKIdentifier,
    WDKSearchConfig,
    WDKStep,
)
from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.services.catalog.param_validation import ValidatedParams
from pathfinder.services.conversations import strategy_ops
from pathfinder.services.strategies import commit as commit_module
from pathfinder.services.strategies import insert_saved as insert_saved_module
from pathfinder.services.strategies import spec_build, step_wdk_push
from pathfinder.services.strategies import sync as sync_module
from pathfinder.services.strategies.insert_saved import ClonedSavedStrategy
from pathfinder.services.strategies.sync import SyncResult

# The push one writer is held inside while the other writer arrives. Local
# Postgres and a stubbed WDK answer in well under a millisecond, so the
# second writer either reads a stale AST or waits for the lock long before
# this elapses.
_SLOW_PUSH_SECONDS = 0.5

_PARAM_PUSH = "update_step_search_config"
_COMBINE_PUSH = "create_combined_step"


@dataclass
class _SlowAPI:
    """WDK stub where one named push takes a measurable amount of time."""

    slow_call: str = ""
    entered_slow_call: asyncio.Event = field(default_factory=asyncio.Event)
    next_id: int = 9000

    def _alloc(self) -> int:
        self.next_id += 1
        return self.next_id

    async def _maybe_slow(self, name: str) -> None:
        if name != self.slow_call:
            return
        self.entered_slow_call.set()
        await asyncio.sleep(_SLOW_PUSH_SECONDS)

    async def delete_step(self, step_id: int, *, user_id: str | None = None) -> None:
        del step_id, user_id

    async def create_step(
        self,
        spec: NewStepSpec,
        record_type: str,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        del spec, record_type, user_id
        return WDKIdentifier(id=self._alloc())

    async def create_combined_step(
        self,
        spec: CombinedStepSpec,
        record_type: str,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        del spec, record_type, user_id
        await self._maybe_slow(_COMBINE_PUSH)
        return WDKIdentifier(id=self._alloc())

    async def create_transform_step(
        self,
        spec: NewStepSpec,
        input_step_id: int,
        record_type: str = "transcript",
        *,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        del spec, input_step_id, record_type, user_id
        return WDKIdentifier(id=self._alloc())

    async def update_step_search_config(
        self,
        step_id: int,
        search_config: WDKSearchConfig,
        record_type: str,
        search_name: str,
        *,
        user_id: str | None = None,
    ) -> None:
        del step_id, search_config, record_type, search_name, user_id
        await self._maybe_slow(_PARAM_PUSH)

    async def update_step_properties(
        self,
        step_id: int,
        spec: PatchStepSpec,
        *,
        user_id: str | None = None,
    ) -> None:
        del step_id, spec, user_id

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep(
            id=step_id,
            search_name="GenesByText",
            search_config=WDKSearchConfig(parameters={}),
        )


async def _no_reconcile(*_args: Any, **_kwargs: Any) -> None:
    return None


async def _fake_sync(
    *,
    graph: Any,
    sync_state: Any,
    site_id: str,
    strategy_name: str | None = None,
) -> SyncResult:
    del graph, sync_state, site_id, strategy_name
    return SyncResult(
        wdk_strategy_id=555,
        wdk_url="http://test",
        root_step_id=0,
        counts={},
        root_count=None,
        zero_step_ids=[],
        step_count=0,
    )


@pytest.fixture
def slow_api(monkeypatch: pytest.MonkeyPatch) -> _SlowAPI:
    api = _SlowAPI()
    monkeypatch.setattr(commit_module, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(step_wdk_push, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(sync_module, "get_strategy_api", lambda _site_id: api)

    async def _no_incomplete(*_args: Any, **_kwargs: Any) -> set[str]:
        return set()

    monkeypatch.setattr(step_wdk_push, "_validate_plan_params", _no_incomplete)
    monkeypatch.setattr(commit_module, "reconcile_sync_state_with_wdk", _no_reconcile)
    monkeypatch.setattr(commit_module, "sync_strategy_for_site", _fake_sync)
    return api


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
    patch_app_db_engine: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner, patch_app_db_engine
    async with session_maker() as session:
        yield session


def _seed_root(expression: str) -> StrategyStepNode:
    return StrategyStepNode(
        id="step_combine",
        search_name="__combine__",
        operator=CombineOp.UNION,
        primary_input=StrategyStepNode(
            id="step_text",
            search_name="GenesByText",
            parameters={
                "text_expression": StringValue(value=expression),
                "text_fields": MultiPickValue(values=["product"]),
            },
        ),
        secondary_input=StrategyStepNode(
            id="step_go",
            search_name="GenesByGoTerm",
            parameters={"go_term": StringValue(value="GO:0004672")},
        ),
    )


async def _seed(session: AsyncSession) -> tuple[UUID, UUID]:
    user = User(id=uuid4())
    session.add(user)
    await session.flush()
    conv = Conversation(
        id=uuid4(),
        user_id=user.id,
        site_id="plasmodb",
        name="Kinase strategy",
    )
    session.add(conv)
    await session.flush()
    ast = StrategyAst(
        record_type="transcript",
        root=_seed_root("kinase"),
        wdk_step_ids={"step_text": 100, "step_go": 200, "step_combine": 300},
    )
    session.add(
        ConversationStrategy(
            conversation_id=conv.id,
            wdk_strategy_id=555,
            strategy_ast=ast.model_dump(by_alias=True, exclude_none=True, mode="json"),
        ),
    )
    await session.commit()
    return conv.id, user.id


async def _read_ast(
    session_maker: async_sessionmaker[AsyncSession],
    conv_id: UUID,
) -> StrategyAst:
    async with session_maker() as fresh:
        row = await ConversationRepository(fresh).get_strategy(conv_id)
        return StrategyAst.model_validate(row.strategy_ast)


def _text_expression(ast: StrategyAst) -> str:
    leaf = ast.root.primary_input
    assert leaf is not None
    value = leaf.parameters["text_expression"]
    assert isinstance(value, StringValue)
    return value.value


async def _run_overlapping(
    *,
    session_maker: async_sessionmaker[AsyncSession],
    api: _SlowAPI,
    conv_id: UUID,
    user_id: UUID,
    slow_call: str,
) -> None:
    """Start the writer whose push is slow, then the other one on top of it."""
    api.slow_call = slow_call

    async def edit(op: Any) -> None:
        async with session_maker() as session:
            await strategy_ops.apply_operation(
                ConversationRepository(session),
                conv_id,
                user_id,
                site_id="plasmodb",
                op=op,
            )

    param_op = UpdateStepParamsOp(
        step_id="step_text",
        parameters={"text_expression": StringValue(value="phosphatase")},
    )
    operator_op = UpdateCombineOperatorOp(
        step_id="step_combine",
        operator=CombineOp.INTERSECT,
    )
    first, second = (
        (param_op, operator_op) if slow_call == _PARAM_PUSH else (operator_op, param_op)
    )

    async def follower() -> None:
        await api.entered_slow_call.wait()
        await edit(second)

    await asyncio.gather(edit(first), follower())


async def test_a_slow_param_edit_does_not_erase_an_operator_edit(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    slow_api: _SlowAPI,
) -> None:
    conv_id, user_id = await _seed(db_session)

    await _run_overlapping(
        session_maker=session_maker,
        api=slow_api,
        conv_id=conv_id,
        user_id=user_id,
        slow_call=_PARAM_PUSH,
    )

    ast = await _read_ast(session_maker, conv_id)
    assert ast.root.operator == CombineOp.INTERSECT
    assert _text_expression(ast) == "phosphatase"


async def test_a_slow_operator_edit_does_not_erase_a_param_edit(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    slow_api: _SlowAPI,
) -> None:
    conv_id, user_id = await _seed(db_session)

    await _run_overlapping(
        session_maker=session_maker,
        api=slow_api,
        conv_id=conv_id,
        user_id=user_id,
        slow_call=_COMBINE_PUSH,
    )

    ast = await _read_ast(session_maker, conv_id)
    assert _text_expression(ast) == "phosphatase"
    assert ast.root.operator == CombineOp.INTERSECT


_SAVED_WDK_STRATEGY_ID = 7777


@pytest.fixture
def slow_clone(monkeypatch: pytest.MonkeyPatch) -> asyncio.Event:
    """Hold insert-saved inside its WDK read of the saved strategy."""
    entered = asyncio.Event()

    async def _clone(site_id: str, saved_wdk_strategy_id: int) -> ClonedSavedStrategy:
        del site_id
        entered.set()
        await asyncio.sleep(_SLOW_PUSH_SECONDS)
        return ClonedSavedStrategy(
            root=StrategyStepNode(
                id="saved_leaf",
                search_name="GenesByGoTerm",
                parameters={"go_term": StringValue(value="GO:0005515")},
            ),
            name="Binding genes",
            record_type="transcript",
            wdk_strategy_id=saved_wdk_strategy_id,
        )

    monkeypatch.setattr(insert_saved_module, "clone_saved_strategy", _clone)

    async def _passthrough_validation(
        _ctx: Any,
        *,
        parameters: dict[str, ParamValue],
        callbacks: Any,
    ) -> ValidatedParams:
        del callbacks
        return ValidatedParams(params=dict(parameters), record_class="transcript")

    monkeypatch.setattr(spec_build, "validate_parameters", _passthrough_validation)
    monkeypatch.setattr(spec_build, "reconcile_sync_state_with_wdk", _no_reconcile)
    monkeypatch.setattr(spec_build, "sync_strategy_for_site", _fake_sync)
    return entered


def _step_expression(ast: StrategyAst, step_id: str) -> str:
    node = next(n for n in walk(ast.root) if n.id == step_id)
    value = node.parameters["text_expression"]
    assert isinstance(value, StringValue)
    return value.value


def _search_names(ast: StrategyAst) -> list[str]:
    return [node.search_name for node in walk(ast.root)]


async def test_an_insert_saved_and_a_param_edit_both_land(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    slow_api: _SlowAPI,
    slow_clone: asyncio.Event,
) -> None:
    """An edit committed while insert-saved reads WDK survives the insert."""
    conv_id, user_id = await _seed(db_session)

    async def insert() -> None:
        async with session_maker() as session:
            await strategy_ops.insert_saved(
                ConversationRepository(session),
                conv_id,
                user_id,
                strategy_ops.InsertSavedParams(
                    site_id="plasmodb",
                    target_step_id="step_combine",
                    saved_wdk_strategy_id=_SAVED_WDK_STRATEGY_ID,
                    operator=CombineOp.INTERSECT,
                ),
            )

    async def edit() -> None:
        await slow_clone.wait()
        async with session_maker() as session:
            await strategy_ops.apply_operation(
                ConversationRepository(session),
                conv_id,
                user_id,
                site_id="plasmodb",
                op=UpdateStepParamsOp(
                    step_id="step_text",
                    parameters={"text_expression": StringValue(value="phosphatase")},
                ),
            )

    await asyncio.gather(insert(), edit())

    ast = await _read_ast(session_maker, conv_id)
    assert _step_expression(ast, "step_text") == "phosphatase"
    assert _search_names(ast).count("GenesByGoTerm") == 2

    async with session_maker() as fresh:
        row = await ConversationRepository(fresh).get_strategy(conv_id)
    assert row.imported_saved_strategy_ids == [_SAVED_WDK_STRATEGY_ID]
