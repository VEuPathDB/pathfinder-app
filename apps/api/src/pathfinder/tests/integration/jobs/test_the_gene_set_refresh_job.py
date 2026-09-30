"""The refresh job puts the auto-imported set on the root the thread stores."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from assistant_core.platform.db import async_session_factory
from procrastinate.testing import InMemoryConnector
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.strategy import CombineOp
from veupathdb.errors import WDKError
from veupathdb_mcp.wdk import GeneSetWdkContext

from pathfinder.domain.strategy.revision import answer_revision
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.jobs.app import procrastinate_app
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories import (
    ConversationRepository,
    ConversationUpdate,
)
from pathfinder.services.gene_sets import operations
from pathfinder.services.gene_sets.store import GeneSetStore, get_gene_set_store
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.gene_set_refresh import (
    defer_the_gene_set_refresh,
)
from pathfinder.tests._support.gene_set_refresh import (
    RESEARCHER_TOKEN,
    run_refresh_job,
    store_root,
)

# The worker carries the researcher's WDK token into the job.
pytestmark = pytest.mark.usefixtures("worker_seams")

_WDK_STRATEGY = 330_642_473
_SET = "gs-refreshed-by-the-job"
_BUILT = [f"PF3D7_{n:07d}" for n in range(549)]
_UNION = _BUILT[:288]
_INTERSECT = _BUILT[:39]


@pytest.fixture
async def thread(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
    patch_app_db_engine: None,
) -> UUID:
    """A built thread whose auto-imported set holds the first build's genes."""
    del db_cleaner, patch_app_db_engine
    async with session_maker() as session:
        user = User(id=uuid4())
        session.add(user)
        await session.commit()
        repo = ConversationRepository(session)
        created = await repo.create(
            user.id, "plasmodb", assistant_id="pathfinder", name="Kinases"
        )
        await get_gene_set_store().save(
            GeneSet(
                id=_SET,
                name="Kinases",
                site_id="plasmodb",
                gene_ids=list(_BUILT),
                source="strategy",
                user_id=user.id,
                wdk_strategy_id=_WDK_STRATEGY,
                record_type="transcript",
            )
        )
        await repo.update_conversation(
            created.id,
            ConversationUpdate(
                wdk_strategy_id=_WDK_STRATEGY,
                wdk_strategy_id_set=True,
                gene_set_id=_SET,
                gene_set_id_set=True,
                gene_set_auto_imported=True,
            ),
        )
        await session.commit()
    return created.id


class _Site:
    """The root's genes per read, and the token each read ran under."""

    def __init__(self, answers: list[list[str]]) -> None:
        self.answers = answers
        self.tokens: list[str | None] = []

    async def resolve(
        self, site_id: str, gene_ids: list[str], ctx: GeneSetWdkContext
    ) -> tuple[list[str], GeneSetWdkContext, int]:
        del site_id, gene_ids
        self.tokens.append(veupathdb_auth_token_ctx.get())
        return self.answers.pop(0), ctx, 3


def _serve(monkeypatch: pytest.MonkeyPatch, answers: list[list[str]]) -> _Site:
    site = _Site(answers)
    monkeypatch.setattr(operations, "resolve_wdk_context", site.resolve)
    return site


async def _stored() -> GeneSet:
    reloaded = await GeneSetStore().get(_SET)
    assert reloaded is not None
    return reloaded


async def test_the_job_takes_the_stored_root_under_the_researchers_token(
    thread: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    site = _serve(monkeypatch, [list(_UNION)])
    stored = await store_root(thread, CombineOp.UNION)

    await run_refresh_job(thread)

    held = await _stored()
    assert (len(held.gene_ids), held.gene_ids, held.answer_revision) == (
        288,
        _UNION,
        answer_revision(stored),
    )
    assert site.tokens == [RESEARCHER_TOKEN]


async def test_a_second_job_on_the_same_root_reads_nothing(
    thread: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    site = _serve(monkeypatch, [list(_UNION)])
    await store_root(thread, CombineOp.UNION)

    await run_refresh_job(thread)
    await run_refresh_job(thread)

    assert (len(site.tokens), len((await _stored()).gene_ids)) == (1, 288)


async def test_a_job_after_a_new_root_takes_the_new_answer(
    thread: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve(monkeypatch, [list(_UNION), list(_INTERSECT)])
    await store_root(thread, CombineOp.UNION)
    await run_refresh_job(thread)
    stored = await store_root(thread, CombineOp.INTERSECT)

    await run_refresh_job(thread)

    held = await _stored()
    assert (held.gene_ids, held.answer_revision) == (
        _INTERSECT,
        answer_revision(stored),
    )


async def test_a_failed_read_leaves_the_set_and_ends_the_job(
    thread: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _timed_out(*_args: object) -> None:
        msg = "the standard report timed out"
        raise WDKError(msg, status=504)

    monkeypatch.setattr(operations, "resolve_wdk_context", _timed_out)
    await store_root(thread, CombineOp.UNION)

    await run_refresh_job(thread)

    held = await _stored()
    assert (len(held.gene_ids), held.answer_revision) == (549, None)


async def test_two_writes_queue_one_job_the_worker_runs(
    thread: UUID,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _serve(monkeypatch, [list(_INTERSECT)])
    written = StrategyMutationContext(
        site_id="plasmodb",
        strategy_session=StrategySession(site_id="plasmodb"),
        conversation_id=thread,
        db_session_factory=async_session_factory,
    )
    await store_root(thread, CombineOp.UNION)
    await defer_the_gene_set_refresh(written)
    await store_root(thread, CombineOp.INTERSECT)
    await defer_the_gene_set_refresh(written)

    queued = [job["lock"] for job in in_memory_jobs.jobs.values()]
    async with procrastinate_app.open_async():
        await procrastinate_app.run_worker_async(
            queues=["default"],
            wait=False,
            listen_notify=False,
            install_signal_handlers=False,
        )

    assert queued == [f"gene-set-refresh:{thread}"]
    assert ((await _stored()).gene_ids, len(site.tokens)) == (_INTERSECT, 1)
