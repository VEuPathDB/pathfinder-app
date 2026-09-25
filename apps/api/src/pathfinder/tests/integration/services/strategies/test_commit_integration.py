"""Integration tests for the ``apply_and_commit`` pipeline."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import (
    StrategyAst,
    walk,
)
from veupathdb.errors import ValidationError

from pathfinder.domain.strategy.operations import (
    AddLeafOp,
    AttachNewRoot,
    DeleteResolution,
    DeleteStepOp,
    UpdateStepMetaOp,
    UpdateStepParamsOp,
)
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.services.strategies import (
    commit,
)
from pathfinder.services.strategies.commit import (
    apply_and_commit,
    apply_operations_and_commit,
)
from pathfinder.tests._support.recorded_searches import suite_search
from pathfinder.tests._support.wdk_write_stubs import (
    RecordedPushes,
    landed_pushes,
    validate_against,
)
from pathfinder.tests.integration.services.strategies._commit_wire import (
    PROMPT,
    PV,
    CountingAPI,
    FailingAPI,
    build_deps,
    combine,
    leaf,
    orphaned,
    patch_strategy_api,
    seed_conversation,
)


@pytest.fixture
def pushes() -> RecordedPushes:
    return landed_pushes(42)


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch, pushes: RecordedPushes) -> CountingAPI:
    api = CountingAPI()
    patch_strategy_api(monkeypatch, api)
    monkeypatch.setattr(commit, "sync_strategy_for_site", pushes.sync)
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


async def test_delete_collapse_combine_drops_wdk_steps_and_persists_ast(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    stub_api: CountingAPI,
    pushes: RecordedPushes,
) -> None:
    a = leaf("step_a")
    b = leaf("step_b")
    c = combine("step_c", a, b)
    wdk_ids = {"step_a": 100, "step_b": 200, "step_c": 300}
    conv_id = await seed_conversation(
        db_session,
        seed_user,
        root=c,
        wdk_step_ids=wdk_ids,
    )
    deps = build_deps(
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
    assert orphaned(stub_api) == [[100, 300]]
    assert pushes.pushed == [(None, PROMPT)]

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
    stub_api: CountingAPI,
) -> None:
    """An empty graph has no root, so the persisted AST must be cleared."""
    a = leaf("step_a")
    conv_id = await seed_conversation(
        db_session,
        seed_user,
        root=a,
        wdk_step_ids={"step_a": 100},
    )
    deps = build_deps(
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

    assert orphaned(stub_api) == [[100]]

    async with session_maker() as fresh:
        repo = ConversationRepository(fresh)
        refetched = await repo.get_strategy(conv_id)
        assert not refetched.strategy_ast
        assert refetched.step_count == 0


async def test_update_step_meta_persists_without_wdk_delete(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    stub_api: CountingAPI,
) -> None:
    a = leaf("step_a")
    conv_id = await seed_conversation(
        db_session,
        seed_user,
        root=a,
        wdk_step_ids={"step_a": 100},
    )
    deps = build_deps(
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
    stub_api: CountingAPI,
) -> None:
    """A batch of operations costs one sync, whatever its length."""
    a = leaf("step_a")
    conv_id = await seed_conversation(
        db_session, seed_user, root=a, wdk_step_ids={"step_a": 100}
    )
    deps = build_deps(
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
    stub_api: CountingAPI,
) -> None:
    """A batch that fails partway leaves the graph exactly as it was."""
    a = leaf("step_a")
    conv_id = await seed_conversation(
        db_session, seed_user, root=a, wdk_step_ids={"step_a": 100}
    )
    deps = build_deps(
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
    stub_api: CountingAPI,
) -> None:
    """Restore rebuilds the whole tree, not only the last operation."""
    a, b = leaf("step_a"), leaf("step_b")
    c = combine("step_c", a, b)
    wdk_ids = {"step_a": 100, "step_b": 200, "step_c": 300}
    conv_id = await seed_conversation(
        db_session, seed_user, root=c, wdk_step_ids=wdk_ids
    )
    deps = build_deps(
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
    stub_api: CountingAPI,
) -> None:
    """A strategy with two roots is a valid intermediate state and persists."""
    a = leaf("step_a")
    conv_id = await seed_conversation(
        db_session, seed_user, root=a, wdk_step_ids={"step_a": 100}
    )
    deps = build_deps(
        conv_id=conv_id,
        root=a,
        wdk_step_ids={"step_a": 100},
        db_session_factory=session_maker,
    )

    await apply_and_commit(
        deps=deps,
        op=AddLeafOp(step=leaf("step_b"), attach=AttachNewRoot()),
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
    stub_api: CountingAPI,
) -> None:
    """A re-read after the commit returns the post-operation state."""
    a = leaf("step_a")
    conv_id = await seed_conversation(
        db_session, seed_user, root=a, wdk_step_ids={"step_a": 100}
    )
    deps = build_deps(
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
        op=AddLeafOp(step=leaf("step_b"), attach=AttachNewRoot()),
    )

    db_session.expire_all()
    refreshed = await outer.get_strategy(conv_id)
    persisted = StrategyAst.model_validate(refreshed.strategy_ast)
    ids = {node.id for node in walk(persisted.root)}
    for detached in persisted.detached_roots:
        ids |= {node.id for node in walk(detached)}
    assert ids == {"step_a", "step_b"}


async def test_a_partial_push_leaves_every_store_agreeing(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A step WDK rejects is a per-step failure; memory, Postgres and the reply agree."""
    api = FailingAPI()
    patch_strategy_api(monkeypatch, api)
    validate_against(monkeypatch, [suite_search("search_genes_by_taxon")])

    a = leaf("step_a")
    conv_id = await seed_conversation(
        db_session, seed_user, root=a, wdk_step_ids={"step_a": 100}
    )
    deps = build_deps(
        conv_id=conv_id,
        root=a,
        wdk_step_ids={"step_a": 100},
        db_session_factory=session_maker,
    )

    # The operation reports what landed instead of raising.
    result = await apply_and_commit(
        deps=deps,
        op=UpdateStepParamsOp(step_id="step_a", parameters={"organism": PV}),
    )

    assert result.failed_step_ids == ["step_a"]

    graph = deps.strategy_session.get_graph(None)
    assert graph is not None
    assert graph.steps["step_a"].parameters == {"organism": PV}

    async with session_maker() as fresh:
        refetched = await ConversationRepository(fresh).get_strategy(conv_id)
        ast = StrategyAst.model_validate(refetched.strategy_ast)
        assert ast.root.parameters == {"organism": PV}
        # The rejection is durable and attributed to the step that caused it.
        assert (ast.wdk_push_errors or {}).get("step_a")


async def test_an_edit_the_recorded_vocabulary_lacks_is_refused(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    stub_api: CountingAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The edit path validates against the site's definition before it writes."""
    validate_against(monkeypatch, [suite_search("search_genes_by_taxon")])
    a = leaf("step_a")
    conv_id = await seed_conversation(
        db_session, seed_user, root=a, wdk_step_ids={"step_a": 100}
    )
    deps = build_deps(
        conv_id=conv_id,
        root=a,
        wdk_step_ids={"step_a": 100},
        db_session_factory=session_maker,
    )

    with pytest.raises(ValidationError) as excinfo:
        await apply_and_commit(
            deps=deps,
            op=UpdateStepParamsOp(
                step_id="step_a",
                parameters={"organism": MultiPickValue(values=["Plasmodium nobody"])},
            ),
        )

    assert "Plasmodium nobody" in str(excinfo.value)
    assert [c.name for c in stub_api.calls] == []
