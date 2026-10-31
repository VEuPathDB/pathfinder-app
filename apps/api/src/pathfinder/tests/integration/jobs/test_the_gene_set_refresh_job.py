"""The refresh job puts the auto-imported set on the root the thread stores."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from assistant_core.platform.db import async_session_factory
from procrastinate.testing import InMemoryConnector
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree
from veupathdb.errors import WDKError
from veupathdb.wdk import (
    WDKSearchConfig,
    WDKStep,
    WDKStepTree,
    WDKStrategyDetails,
    walk_wdk_step_tree,
)

from pathfinder.domain.strategy.revision import answer_revision
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.jobs.app import procrastinate_app
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories import (
    ConversationRepository,
    ConversationUpdate,
)
from pathfinder.services.gene_sets import operations, strategy_genes
from pathfinder.services.gene_sets.homes import StepGenes
from pathfinder.services.gene_sets.step_genes import TooManyGenesError
from pathfinder.services.gene_sets.store import GeneSetStore, get_gene_set_store
from pathfinder.services.gene_sets.strategy_genes import (
    RecordsAreNotGenesError,
)
from pathfinder.services.gene_sets.types import (
    GeneSet,
    OutOfDate,
    ResultAboveTheCap,
    ResultNotGenes,
    ResultWithoutGenes,
)
from pathfinder.services.strategies import sync
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.gene_set_refresh import (
    defer_the_gene_set_refresh,
)
from pathfinder.services.strategies.strategy_line import (
    postgres_strategy_line,
    use_strategy_line,
)
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.gene_set_refresh import (
    RESEARCHER_TOKEN,
    RootAnswer,
    run_refresh_job,
    serve_roots,
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


async def _stored() -> GeneSet:
    reloaded = await GeneSetStore().get(_SET)
    assert reloaded is not None
    return reloaded


async def test_the_job_takes_the_stored_root_under_the_researchers_token(
    thread: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    site = serve_roots(monkeypatch, [RootAnswer(_UNION)])
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
    site = serve_roots(monkeypatch, [RootAnswer(_UNION)])
    await store_root(thread, CombineOp.UNION)

    await run_refresh_job(thread)
    await run_refresh_job(thread)

    assert (len(site.tokens), len((await _stored()).gene_ids)) == (1, 288)


async def test_a_job_after_a_new_root_takes_the_new_answer(
    thread: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    serve_roots(monkeypatch, [RootAnswer(_UNION), RootAnswer(_INTERSECT)])
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
    async def _timed_out(*_args: object, **_kwargs: object) -> None:
        msg = "the standard report timed out"
        raise WDKError(msg, status=504)

    monkeypatch.setattr(operations, "read_strategy_genes", _timed_out)
    await store_root(thread, CombineOp.UNION)

    await run_refresh_job(thread)

    held = await _stored()
    assert (len(held.gene_ids), held.answer_revision) == (549, None)


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (
            RootAnswer(refusal=TooManyGenesError(309_068, 10_000)),
            ResultAboveTheCap(count=309_068, cap=10_000),
        ),
        (
            RootAnswer(refusal=RecordsAreNotGenesError("group")),
            ResultNotGenes(record_class="group"),
        ),
        (RootAnswer([]), ResultWithoutGenes()),
    ],
)
async def test_a_refused_root_marks_the_set_out_of_date(
    thread: UUID,
    monkeypatch: pytest.MonkeyPatch,
    answer: RootAnswer,
    reason: OutOfDate,
) -> None:
    serve_roots(monkeypatch, [answer])
    await store_root(thread, CombineOp.UNION)

    await run_refresh_job(thread)

    held = await _stored()
    assert (len(held.gene_ids), held.answer_revision, held.out_of_date) == (
        549,
        None,
        reason,
    )


async def test_a_later_root_within_the_cap_clears_the_mark(
    thread: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    serve_roots(
        monkeypatch,
        [
            RootAnswer(refusal=TooManyGenesError(309_068, 10_000)),
            RootAnswer(_INTERSECT),
        ],
    )
    await store_root(thread, CombineOp.UNION)
    await run_refresh_job(thread)
    stored = await store_root(thread, CombineOp.INTERSECT)

    await run_refresh_job(thread)

    held = await _stored()
    assert (held.gene_ids, held.answer_revision, held.out_of_date) == (
        _INTERSECT,
        answer_revision(stored),
        None,
    )


async def test_the_root_the_set_holds_put_back_clears_the_mark(
    thread: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    site = serve_roots(
        monkeypatch,
        [
            RootAnswer(_UNION),
            RootAnswer(refusal=TooManyGenesError(309_068, 10_000)),
            RootAnswer(_UNION),
        ],
    )
    held_root = await store_root(thread, CombineOp.UNION)
    await run_refresh_job(thread)
    await store_root(thread, CombineOp.INTERSECT)
    await run_refresh_job(thread)
    await store_root(thread, CombineOp.UNION)

    await run_refresh_job(thread)

    held = await _stored()
    assert (held.gene_ids, held.answer_revision, held.out_of_date) == (
        _UNION,
        answer_revision(held_root),
        None,
    )
    assert len(site.tokens) == 3


async def test_two_writes_queue_one_job_the_worker_runs(
    thread: UUID,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = serve_roots(monkeypatch, [RootAnswer(_INTERSECT)])
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


_TEXT, _GO, _JOIN, _SIGNAL, _OUTER = (
    227283340,
    227283350,
    227283440,
    227283370,
    227283450,
)
_BEFORE_THE_DELETE = WDKStepTree(
    step_id=_OUTER,
    primary_input=WDKStepTree(
        step_id=_JOIN,
        primary_input=WDKStepTree(step_id=_TEXT),
        secondary_input=WDKStepTree(step_id=_GO),
    ),
    secondary_input=WDKStepTree(step_id=_SIGNAL),
)
_AFTER_THE_DELETE = WDKStepTree(
    step_id=_JOIN,
    primary_input=WDKStepTree(step_id=_TEXT),
    secondary_input=WDKStepTree(step_id=_GO),
)
_WAITING_ON_A_LINE = text(
    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted"
)


class _ReadSavesBack:
    def __init__(self) -> None:
        self.held = _BEFORE_THE_DELETE
        self.put_started = asyncio.Event()
        self.release_the_put = asyncio.Event()
        self.reads: list[int] = []

    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del user_id
        loaded = self.held
        self.reads.append(loaded.step_id)
        await asyncio.sleep(0)
        self.held = loaded
        return WDKStrategyDetails(
            strategy_id=strategy_id,
            name="Kinases",
            root_step_id=loaded.step_id,
            record_class_name="transcript",
            step_tree=loaded,
            steps={
                str(node.step_id): WDKStep(
                    id=node.step_id,
                    search_name="GenesByText",
                    search_config=WDKSearchConfig(parameters={}),
                    record_class_name="transcript",
                    estimated_size=48,
                )
                for node in walk_wdk_step_tree(loaded)
            },
        )

    async def update_strategy(
        self,
        strategy_id: int,
        step_tree: WDKStepTree | None = None,
        name: str | None = None,
        user_id: str | None = None,
        *,
        description: str | None = None,
    ) -> WDKStrategyDetails:
        del name, user_id, description
        if step_tree is not None:
            self.put_started.set()
            await self.release_the_put.wait()
            self.held = step_tree
        return await self.get_strategy(strategy_id)


@pytest.fixture
def postgres_line() -> Iterator[None]:
    previous = use_strategy_line(postgres_strategy_line(async_session_factory))
    try:
        yield
    finally:
        use_strategy_line(previous)


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> _ReadSavesBack:
    served = _ReadSavesBack()
    monkeypatch.setattr(sync, "get_strategy_api", lambda _site_id: served)
    monkeypatch.setattr(strategy_genes, "get_strategy_api", lambda _site_id: served)

    async def _genes(_site_id: str, _root: WDKStep) -> StepGenes:
        return StepGenes(gene_ids=list(_INTERSECT), homes={}, record_class="transcript")

    monkeypatch.setattr(strategy_genes, "read_genes_of", _genes)
    return served


def _graph_after_the_delete() -> StrategyGraph:
    graph = StrategyGraph("g1", "Kinases", "plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="join",
            search_name="__combine__",
            primary_input=StrategyStepNode(id="text", search_name="GenesByText"),
            secondary_input=StrategyStepNode(id="go", search_name="GenesByGoTerm"),
            operator=CombineOp.INTERSECT,
        )
    )
    for step in graph.steps.values():
        step.record_class = "transcript"
    graph.recompute_roots()
    return graph


async def _a_request_waits_on_a_line() -> None:
    async with asyncio.timeout(10):
        while True:
            async with async_session_factory() as session:
                if await session.scalar(_WAITING_ON_A_LINE):
                    return
            await asyncio.sleep(0.05)


@pytest.mark.usefixtures("postgres_line")
async def test_the_job_reads_the_strategy_after_the_tree_write_ends(
    thread: UUID, site: _ReadSavesBack
) -> None:
    await store_root(thread, CombineOp.INTERSECT)
    save = asyncio.create_task(
        sync.sync_strategy_for_site(
            graph=_graph_after_the_delete(),
            sync_state=WDKSyncState(
                wdk_step_ids={"text": _TEXT, "go": _GO, "join": _JOIN},
                wdk_strategy_id=_WDK_STRATEGY,
                wdk_step_tree=_BEFORE_THE_DELETE,
                wdk_strategy_name="Kinases",
            ),
            site_id="plasmodb",
        )
    )
    await site.put_started.wait()
    refresh = asyncio.create_task(run_refresh_job(thread))
    await _a_request_waits_on_a_line()
    read_during_the_write = list(site.reads)

    site.release_the_put.set()
    await asyncio.gather(save, refresh)

    assert read_during_the_write == []
    assert site.reads == [_JOIN, _JOIN, _JOIN]
    assert site.held == _AFTER_THE_DELETE
    assert (await _stored()).gene_ids == _INTERSECT
