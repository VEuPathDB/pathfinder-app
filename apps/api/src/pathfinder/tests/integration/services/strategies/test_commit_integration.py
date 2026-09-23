"""Integration tests for the ``apply_and_commit`` pipeline."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import (
    CombineOp,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
    walk,
)
from veupathdb.errors import WDKError
from veupathdb.wdk import (
    CombinedStepSpec,
    NewStepSpec,
    PatchStepSpec,
    WDKIdentifier,
    WDKSearchConfig,
    WDKStep,
)

from pathfinder.domain.strategy.operations import (
    AddLeafOp,
    AttachNewRoot,
    DeleteResolution,
    DeleteStepOp,
    UpdateStepMetaOp,
    UpdateStepParamsOp,
)
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies import (
    commit,
    step_wdk_push,
    sync,
)
from pathfinder.services.strategies.commit import (
    apply_and_commit,
    apply_operations_and_commit,
)
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.sync import SyncResult
from pathfinder.services.strategies.sync_state import WDKSyncState


@dataclass
class _Call:
    name: str
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass
class _CountingAPI:
    calls: list[_Call] = field(default_factory=list)
    next_id: int = 9000

    def _alloc(self) -> int:
        self.next_id += 1
        return self.next_id

    async def delete_step(self, step_id: int, *, user_id: str | None = None) -> None:
        del user_id
        self.calls.append(_Call("delete_step", {"step_id": step_id}))

    async def create_step(
        self,
        spec: NewStepSpec,
        record_type: str,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        del user_id
        self.calls.append(
            _Call(
                "create_step",
                {"search_name": spec.search_name, "record_type": record_type},
            ),
        )
        return WDKIdentifier(id=self._alloc())

    async def create_combined_step(
        self,
        spec: CombinedStepSpec,
        record_type: str,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        del user_id
        self.calls.append(
            _Call(
                "create_combined_step",
                {
                    "primary_step_id": spec.primary_step_id,
                    "secondary_step_id": spec.secondary_step_id,
                    "boolean_operator": spec.boolean_operator.value,
                    "record_type": record_type,
                },
            ),
        )
        return WDKIdentifier(id=self._alloc())

    async def create_transform_step(
        self,
        spec: NewStepSpec,
        input_step_id: int,
        record_type: str = "transcript",
        *,
        user_id: str | None = None,
    ) -> WDKIdentifier:
        del user_id
        self.calls.append(
            _Call(
                "create_transform_step",
                {
                    "search_name": spec.search_name,
                    "input_step_id": input_step_id,
                    "record_type": record_type,
                },
            ),
        )
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
        del user_id
        self.calls.append(
            _Call(
                "update_step_search_config",
                {
                    "step_id": step_id,
                    "search_name": search_name,
                    "record_type": record_type,
                    "parameters": dict(search_config.parameters),
                },
            ),
        )

    async def update_step_properties(
        self,
        step_id: int,
        spec: PatchStepSpec,
        *,
        user_id: str | None = None,
    ) -> None:
        del user_id
        self.calls.append(
            _Call("update_step_properties", {"step_id": step_id, "spec": spec})
        )

    async def delete_orphaned_steps(self, step_ids: list[int]) -> list[int]:
        """Delete every id and name the ones the site kept. This fake keeps none."""
        self.calls.append(_Call("delete_orphaned_steps", {"step_ids": list(step_ids)}))
        for step_id in step_ids:
            await self.delete_step(step_id)
        return []

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep(
            id=step_id,
            search_name="GenesByTaxon",
            search_config=WDKSearchConfig(parameters={}),
        )


async def _fake_sync(
    *,
    graph: Any,
    sync_state: Any,
    site_id: str,
    strategy_name: str | None = None,
) -> SyncResult:
    del graph, sync_state, site_id, strategy_name
    return SyncResult(
        wdk_strategy_id=42,
        wdk_url="http://test",
        root_step_id=0,
        counts={},
        root_count=None,
        zero_step_ids=[],
        step_count=0,
    )


def _patch_strategy_api(monkeypatch: pytest.MonkeyPatch, api: _CountingAPI) -> None:
    """Serve ``api`` to the commit path, and let every step count as complete."""

    async def _noop_validate(*_args: Any, **_kwargs: Any) -> set[str]:
        return set()

    async def _noop_reconcile(*_args: Any, **_kwargs: Any) -> None:
        return None

    for module in (commit, step_wdk_push, sync):
        monkeypatch.setattr(module, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(step_wdk_push, "_validate_plan_params", _noop_validate)
    monkeypatch.setattr(commit, "reconcile_sync_state_with_wdk", _noop_reconcile)


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> _CountingAPI:
    api = _CountingAPI()
    _patch_strategy_api(monkeypatch, api)
    monkeypatch.setattr(commit, "sync_strategy_for_site", _fake_sync)
    return api


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


@pytest.fixture
async def seed_user(db_session: AsyncSession) -> User:
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    return user


def _orphaned(api: _CountingAPI) -> list[list[int]]:
    """The WDK step ids handed to each orphan sweep, in call order."""
    return [
        sorted(c.kwargs["step_ids"])
        for c in api.calls
        if c.name == "delete_orphaned_steps"
    ]


_PV = MultiPickValue(values=["Plasmodium vivax PvW1"])


def _leaf(id_: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=id_,
        search_name="GenesByTaxon",
        parameters={"organism": MultiPickValue(values=["Pf3D7"])},
    )


def _combine(
    id_: str,
    p: StrategyStepNode,
    s: StrategyStepNode,
    op: CombineOp = CombineOp.INTERSECT,
) -> StrategyStepNode:
    return StrategyStepNode(
        id=id_,
        search_name="__combine__",
        primary_input=p,
        secondary_input=s,
        operator=op,
    )


async def _seed_conversation(
    db_session: AsyncSession,
    user: User,
    *,
    root: StrategyStepNode,
    wdk_step_ids: dict[str, int],
) -> UUID:
    ast = StrategyAst(record_type="transcript", root=root, wdk_step_ids=wdk_step_ids)
    conv = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        id=uuid4(),
        user_id=user.id,
        site_id="plasmodb",
        name="Test strategy",
    )
    db_session.add(conv)
    await db_session.flush()
    db_session.add(
        ConversationStrategy(
            conversation_id=conv.id,
            wdk_strategy_id=555,
            strategy_ast=ast.model_dump(by_alias=True, exclude_none=True, mode="json"),
        ),
    )
    await db_session.commit()
    return conv.id


def _build_deps(
    *,
    conv_id: UUID,
    root: StrategyStepNode,
    wdk_step_ids: dict[str, int],
    db_session_factory: Any,
) -> StrategyMutationContext:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(
        graph_id=str(conv_id), name="Test strategy", site_id="plasmodb"
    )
    graph.record_type = "transcript"
    graph.steps.update(flatten_tree(root))
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids=dict(wdk_step_ids),
        wdk_strategy_id=555,
    )
    return StrategyMutationContext(
        site_id="plasmodb",
        strategy_session=session,
        conversation_id=conv_id,
        db_session_factory=db_session_factory,
    )


async def test_delete_collapse_combine_drops_wdk_steps_and_persists_ast(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    stub_api: _CountingAPI,
) -> None:
    a = _leaf("step_a")
    b = _leaf("step_b")
    c = _combine("step_c", a, b)
    wdk_ids = {"step_a": 100, "step_b": 200, "step_c": 300}
    conv_id = await _seed_conversation(
        db_session,
        seed_user,
        root=c,
        wdk_step_ids=wdk_ids,
    )
    deps = _build_deps(
        conv_id=conv_id,
        root=c,
        wdk_step_ids=wdk_ids,
        db_session_factory=session_maker,
    )

    result = await apply_and_commit(
        deps=deps,
        op=DeleteStepOp(
            step_id="step_a",
            resolution=DeleteResolution.COLLAPSE_COMBINE,
        ),
    )

    assert sorted(result.dropped_step_ids) == ["step_a", "step_c"]
    assert _orphaned(stub_api) == [[100, 300]]

    async with session_maker() as fresh:
        repo = ConversationRepository(fresh)
        refetched = await repo.get_strategy(conv_id)
        ast = StrategyAst.model_validate(refetched.strategy_ast)
        assert ast.root.id == "step_b"
        assert ast.root.primary_input is None
        assert ast.root.secondary_input is None


async def test_deleting_the_whole_strategy_clears_the_persisted_ast(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    stub_api: _CountingAPI,
) -> None:
    """An empty graph has no root, so the persisted AST must be cleared."""
    a = _leaf("step_a")
    conv_id = await _seed_conversation(
        db_session,
        seed_user,
        root=a,
        wdk_step_ids={"step_a": 100},
    )
    deps = _build_deps(
        conv_id=conv_id,
        root=a,
        wdk_step_ids={"step_a": 100},
        db_session_factory=session_maker,
    )

    await apply_and_commit(
        deps=deps,
        op=DeleteStepOp(
            step_id="step_a",
            resolution=DeleteResolution.DELETE_STRATEGY,
        ),
    )

    assert _orphaned(stub_api) == [[100]]

    async with session_maker() as fresh:
        repo = ConversationRepository(fresh)
        refetched = await repo.get_strategy(conv_id)
        assert not refetched.strategy_ast
        assert refetched.step_count == 0


async def test_update_step_meta_persists_without_wdk_delete(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    stub_api: _CountingAPI,
) -> None:
    a = _leaf("step_a")
    conv_id = await _seed_conversation(
        db_session,
        seed_user,
        root=a,
        wdk_step_ids={"step_a": 100},
    )
    deps = _build_deps(
        conv_id=conv_id,
        root=a,
        wdk_step_ids={"step_a": 100},
        db_session_factory=session_maker,
    )

    await apply_and_commit(
        deps=deps,
        op=UpdateStepMetaOp(step_id="step_a", display_name="Renamed step"),
    )

    deletes = [c for c in stub_api.calls if c.name == "delete_step"]
    assert deletes == []

    async with session_maker() as fresh:
        repo = ConversationRepository(fresh)
        refetched = await repo.get_strategy(conv_id)
        ast = StrategyAst.model_validate(refetched.strategy_ast)
        assert ast.root.display_name == "Renamed step"


async def test_a_batch_of_operations_lands_in_one_commit(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    stub_api: _CountingAPI,
) -> None:
    """A batch of operations costs one sync, whatever its length."""
    a = _leaf("step_a")
    conv_id = await _seed_conversation(
        db_session, seed_user, root=a, wdk_step_ids={"step_a": 100}
    )
    deps = _build_deps(
        conv_id=conv_id,
        root=a,
        wdk_step_ids={"step_a": 100},
        db_session_factory=session_maker,
    )

    result = await apply_operations_and_commit(
        deps=deps,
        ops=[
            UpdateStepMetaOp(step_id="step_a", display_name="Renamed once"),
            UpdateStepMetaOp(step_id="step_a", display_name="Renamed twice"),
        ],
    )

    assert "Renamed" not in result.description or result.description.count(";") == 1
    graph = deps.strategy_session.get_graph(None)
    assert graph is not None
    assert graph.steps["step_a"].display_name == "Renamed twice"

    async with session_maker() as fresh:
        refetched = await ConversationRepository(fresh).get_strategy(conv_id)
        ast = StrategyAst.model_validate(refetched.strategy_ast)
        assert ast.root.display_name == "Renamed twice"


async def test_a_rejected_batch_changes_nothing(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    stub_api: _CountingAPI,
) -> None:
    """A batch that fails partway leaves the graph exactly as it was."""
    a = _leaf("step_a")
    conv_id = await _seed_conversation(
        db_session, seed_user, root=a, wdk_step_ids={"step_a": 100}
    )
    deps = _build_deps(
        conv_id=conv_id,
        root=a,
        wdk_step_ids={"step_a": 100},
        db_session_factory=session_maker,
    )

    with pytest.raises(ApplyError):
        await apply_operations_and_commit(
            deps=deps,
            ops=[
                UpdateStepMetaOp(step_id="step_a", display_name="Applied first"),
                UpdateStepMetaOp(step_id="ghost", display_name="never exists"),
            ],
        )

    graph = deps.strategy_session.get_graph(None)
    assert graph is not None
    assert sorted(graph.steps) == ["step_a"]
    # The first rename must not survive the rejected batch.
    assert graph.steps["step_a"].display_name != "Applied first"

    async with session_maker() as fresh:
        refetched = await ConversationRepository(fresh).get_strategy(conv_id)
        ast = StrategyAst.model_validate(refetched.strategy_ast)
        assert ast.root.display_name != "Applied first"


async def test_a_rejected_batch_restores_a_multi_step_shape(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    stub_api: _CountingAPI,
) -> None:
    """Restore rebuilds the whole tree, not only the last operation."""
    a, b = _leaf("step_a"), _leaf("step_b")
    c = _combine("step_c", a, b)
    wdk_ids = {"step_a": 100, "step_b": 200, "step_c": 300}
    conv_id = await _seed_conversation(
        db_session, seed_user, root=c, wdk_step_ids=wdk_ids
    )
    deps = _build_deps(
        conv_id=conv_id,
        root=c,
        wdk_step_ids=wdk_ids,
        db_session_factory=session_maker,
    )

    with pytest.raises(ApplyError):
        await apply_operations_and_commit(
            deps=deps,
            ops=[
                DeleteStepOp(
                    step_id="step_a", resolution=DeleteResolution.COLLAPSE_COMBINE
                ),
                UpdateStepMetaOp(step_id="ghost", display_name="never exists"),
            ],
        )

    graph = deps.strategy_session.get_graph(None)
    assert graph is not None
    assert sorted(graph.steps) == ["step_a", "step_b", "step_c"]
    assert graph.roots == {"step_c"}
    assert graph.steps["step_c"].primary_input_id == "step_a"
    assert graph.steps["step_c"].secondary_input_id == "step_b"


async def test_adding_a_second_root_step_is_persisted(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    stub_api: _CountingAPI,
) -> None:
    """A strategy with two roots is a valid intermediate state and persists."""
    a = _leaf("step_a")
    conv_id = await _seed_conversation(
        db_session, seed_user, root=a, wdk_step_ids={"step_a": 100}
    )
    deps = _build_deps(
        conv_id=conv_id,
        root=a,
        wdk_step_ids={"step_a": 100},
        db_session_factory=session_maker,
    )

    await apply_and_commit(
        deps=deps,
        op=AddLeafOp(step=_leaf("step_b"), attach=AttachNewRoot()),
    )

    graph = deps.strategy_session.get_graph(None)
    assert graph is not None
    assert graph.roots == {"step_a", "step_b"}

    async with session_maker() as fresh:
        refetched = await ConversationRepository(fresh).get_strategy(conv_id)
        persisted = StrategyAst.model_validate(refetched.strategy_ast)
        ids = {node.id for node in walk(persisted.root)}
        for detached in persisted.detached_roots:
            ids |= {node.id for node in walk(detached)}
        assert ids == {"step_a", "step_b"}
        assert refetched.step_count == 2


async def test_the_operation_response_reflects_the_operation(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    stub_api: _CountingAPI,
) -> None:
    """A re-read after the commit returns the post-operation state."""
    a = _leaf("step_a")
    conv_id = await _seed_conversation(
        db_session, seed_user, root=a, wdk_step_ids={"step_a": 100}
    )
    deps = _build_deps(
        conv_id=conv_id,
        root=a,
        wdk_step_ids={"step_a": 100},
        db_session_factory=session_maker,
    )

    # The route reads the row before applying, so the identity map holds it.
    outer = ConversationRepository(db_session)
    assert await outer.get_by_id(conv_id) is not None

    await apply_and_commit(
        deps=deps,
        op=AddLeafOp(step=_leaf("step_b"), attach=AttachNewRoot()),
    )

    db_session.expire_all()
    refreshed = await outer.get_strategy(conv_id)
    persisted = StrategyAst.model_validate(refreshed.strategy_ast)
    ids = {node.id for node in walk(persisted.root)}
    for detached in persisted.detached_roots:
        ids |= {node.id for node in walk(detached)}
    assert ids == {"step_a", "step_b"}


class _FailingAPI(_CountingAPI):
    """Rejects one search name, the way WDK rejects one bad step."""

    fail_search: str = "GenesByTaxon"

    async def update_step_search_config(
        self,
        step_id: int,
        search_config: WDKSearchConfig,
        record_type: str,
        search_name: str,
        *,
        user_id: str | None = None,
    ) -> None:
        if search_name == self.fail_search:
            msg = "WDK rejected this step"
            raise WDKError(msg, 422)
        await super().update_step_search_config(
            step_id, search_config, record_type, search_name, user_id=user_id
        )


async def test_a_partial_push_leaves_every_store_agreeing(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A step WDK rejects is a per-step failure; memory, Postgres and the reply agree."""
    api = _FailingAPI()
    _patch_strategy_api(monkeypatch, api)

    a = _leaf("step_a")
    conv_id = await _seed_conversation(
        db_session, seed_user, root=a, wdk_step_ids={"step_a": 100}
    )
    deps = _build_deps(
        conv_id=conv_id,
        root=a,
        wdk_step_ids={"step_a": 100},
        db_session_factory=session_maker,
    )

    # The operation reports what landed instead of raising.
    result = await apply_and_commit(
        deps=deps,
        op=UpdateStepParamsOp(step_id="step_a", parameters={"organism": _PV}),
    )

    assert result.failed_step_ids == ["step_a"]

    graph = deps.strategy_session.get_graph(None)
    assert graph is not None
    assert graph.steps["step_a"].parameters == {"organism": _PV}

    async with session_maker() as fresh:
        refetched = await ConversationRepository(fresh).get_strategy(conv_id)
        ast = StrategyAst.model_validate(refetched.strategy_ast)
        assert ast.root.parameters == {"organism": _PV}
        # The rejection is durable and attributed to the step that caused it.
        assert (ast.wdk_push_errors or {}).get("step_a")
