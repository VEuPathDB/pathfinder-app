"""The refresh job puts the auto-imported set on the root the thread stores."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from assistant_core.platform.db import async_session_factory
from procrastinate.testing import InMemoryConnector
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree
from veupathdb.errors import WDKError
from veupathdb.wdk import StrategyRequest, WDKStep, strategy_gate, use_strategy_gate
from veupathdb_mcp.strategy_line import install_strategy_line

from pathfinder.domain.strategy.revision import answer_revision
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.jobs.app import procrastinate_app
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories import (
    ConversationRepository,
    ConversationUpdate,
)
from pathfinder.platform.config import get_settings
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
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.gene_set_refresh import (
    RESEARCHER_TOKEN,
    RootAnswer,
    run_refresh_job,
    serve_roots,
    store_root,
)
from pathfinder.tests._support.read_saves_back import (
    AFTER_THE_DELETE,
    BEFORE_THE_DELETE,
    GO,
    INNER,
    TEXT,
    ReadSavesBack,
    strategy_api_on,
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


class _LineWaits:
    def __init__(self) -> None:
        self.inside = 0
        self.a_request_waits = asyncio.Event()


@pytest.fixture
async def strategy_line() -> AsyncIterator[_LineWaits]:
    previous = strategy_gate()
    engine = install_strategy_line(get_settings().database_url)
    installed = strategy_gate()
    waits = _LineWaits()

    @asynccontextmanager
    async def watched(request: StrategyRequest) -> AsyncIterator[None]:
        if waits.inside:
            waits.a_request_waits.set()
        waits.inside += 1
        try:
            async with installed(request):
                yield
        finally:
            waits.inside -= 1

    use_strategy_gate(watched)
    try:
        yield waits
    finally:
        use_strategy_gate(previous)
        await engine.dispose()


@pytest.fixture
async def site(monkeypatch: pytest.MonkeyPatch) -> ReadSavesBack:
    served = ReadSavesBack(put_waits_for_a_reader=False)
    served.release_the_put.clear()
    api = await strategy_api_on(served)
    monkeypatch.setattr(sync, "get_strategy_api", lambda _site_id: api)
    monkeypatch.setattr(strategy_genes, "get_strategy_api", lambda _site_id: api)

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


async def test_the_job_reads_the_strategy_after_the_tree_write_ends(
    thread: UUID, site: ReadSavesBack, strategy_line: _LineWaits
) -> None:
    reset = veupathdb_auth_token_ctx.set(RESEARCHER_TOKEN)
    try:
        await store_root(thread, CombineOp.INTERSECT)
        save = asyncio.create_task(
            sync.sync_strategy_for_site(
                graph=_graph_after_the_delete(),
                sync_state=WDKSyncState(
                    wdk_step_ids={"text": TEXT, "go": GO, "join": INNER},
                    wdk_strategy_id=_WDK_STRATEGY,
                    wdk_step_tree=BEFORE_THE_DELETE,
                    wdk_strategy_name="Kinases",
                ),
                site_id="plasmodb",
            )
        )
        await site.put_started.wait()
        refresh = asyncio.create_task(run_refresh_job(thread))
        async with asyncio.timeout(10):
            await strategy_line.a_request_waits.wait()
        for _ in range(20):
            await asyncio.sleep(0)
        read_during_the_write = list(site.reads)

        site.release_the_put.set()
        await asyncio.gather(save, refresh)
    finally:
        veupathdb_auth_token_ctx.reset(reset)

    assert read_during_the_write == []
    assert site.reads == [INNER, INNER, INNER]
    assert site.held == AFTER_THE_DELETE
    assert (await _stored()).gene_ids == _INTERSECT
