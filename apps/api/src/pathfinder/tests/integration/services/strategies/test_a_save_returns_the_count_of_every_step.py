"""A canvas save answers with the site's count for every step it pushed."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.strategy import CombineOp, StrategyAst

from pathfinder.domain.strategy.operations import (
    AddLeafOp,
    AttachNewRoot,
    UpdateStepParamsOp,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.services.conversations.responses import derive_steps_from_strategy_ast
from pathfinder.services.strategies import commit
from pathfinder.services.strategies.commit import apply_and_commit
from pathfinder.services.strategies.sync import SyncResult
from pathfinder.services.strategies.sync_state import WDKSyncState, ensure_sync_state
from pathfinder.tests._support.recorded_searches import suite_search
from pathfinder.tests._support.wdk_write_stubs import validate_against
from pathfinder.tests.integration.services.strategies._commit_wire import (
    PV,
    CountingAPI,
    FailingAPI,
    build_deps,
    combine,
    leaf,
    patch_strategy_api,
    seed_conversation,
)

pytestmark = pytest.mark.usefixtures("open_job_queue")

SITE_COUNTS = {"step_a": 11, "step_b": 22, "step_c": 5, "step_d": 40}


@dataclass
class SiteThatCounts:
    """A push that stores what the site answers for each step, as the real sync does."""

    pushed: int = 0

    async def sync(
        self,
        *,
        graph: StrategyGraph,
        sync_state: WDKSyncState,
        site_id: str,
        strategy_name: str | None = None,
        user_prompt: str = "",
    ) -> SyncResult:
        del site_id, strategy_name, user_prompt
        self.pushed += 1
        sync_state.step_counts = {sid: SITE_COUNTS.get(sid) for sid in graph.steps}
        return SyncResult(
            wdk_strategy_id=555,
            wdk_url="http://test",
            root_step_id=0,
            counts=dict(sync_state.step_counts),
            root_count=None,
            zero_step_ids=[],
            step_count=len(graph.steps),
        )


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
    await db_session.commit()
    return user


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> SiteThatCounts:
    counting = SiteThatCounts()
    patch_strategy_api(monkeypatch, CountingAPI())
    validate_against(monkeypatch, [suite_search("search_genes_by_taxon")])
    monkeypatch.setattr(commit, "sync_strategy_for_site", counting.sync)
    return counting


async def _sizes(
    session_maker: async_sessionmaker[AsyncSession], conv_id: UUID
) -> dict[str, int | None]:
    async with session_maker() as fresh:
        stored = await ConversationRepository(fresh).get_strategy(conv_id)
    ast = StrategyAst.model_validate(stored.strategy_ast)
    return {
        step.id: step.estimated_size for step in derive_steps_from_strategy_ast(ast)
    }


async def test_an_edit_answers_with_the_count_of_every_step_in_the_tree(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    site: SiteThatCounts,
) -> None:
    root = combine("step_c", leaf("step_a"), leaf("step_b"), CombineOp.UNION)
    ids = {"step_a": 100, "step_b": 101, "step_c": 102}
    conv_id = await seed_conversation(
        db_session, seed_user, root=root, wdk_step_ids=ids
    )
    deps = build_deps(
        conv_id=conv_id, root=root, wdk_step_ids=ids, db_session_factory=session_maker
    )

    await apply_and_commit(
        deps=deps,
        op=UpdateStepParamsOp(step_id="step_a", parameters={"organism": PV}),
    )

    assert site.pushed == 1
    assert await _sizes(session_maker, conv_id) == {
        "step_c": 5,
        "step_a": 11,
        "step_b": 22,
    }


async def test_a_new_step_answers_with_its_count(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    site: SiteThatCounts,
) -> None:
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
        deps=deps, op=AddLeafOp(step=leaf("step_d"), attach=AttachNewRoot())
    )

    assert await _sizes(session_maker, conv_id) == {"step_a": 11, "step_d": 40}
    assert site.pushed == 1


async def test_a_step_the_site_refused_answers_with_no_count(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_strategy_api(monkeypatch, FailingAPI())
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
    ensure_sync_state(deps.strategy_session).step_counts["step_a"] = 7

    result = await apply_and_commit(
        deps=deps,
        op=UpdateStepParamsOp(step_id="step_a", parameters={"organism": PV}),
    )

    assert result.failed_step_ids == ["step_a"]
    assert await _sizes(session_maker, conv_id) == {"step_a": None}
