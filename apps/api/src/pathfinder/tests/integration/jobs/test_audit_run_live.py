"""Audit runs against QA through their own queue: the recorded positives, and one genome screened."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from assistant_core.platform.db import async_session_factory
from procrastinate.testing import InMemoryConnector
from veupathdb import NoObserver, set_observer
from veupathdb.auth_context import veupathdb_auth_token_ctx

from pathfinder.domain.audit.findings import AuditOutcome
from pathfinder.domain.audit.scope import AuditScope, GenePairTarget
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
)
from pathfinder.platform.metrics import PathfinderObserver
from pathfinder.services.audit.job import outcome, start_run
from pathfinder.services.audit.runs import create_run
from pathfinder.tests._support.audit import (
    GT1_SELK,
    ME49_SELK,
    NF54,
    PIGA,
    seed_thread,
)
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.jobs._audit_jobs import queued, work

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

COMPARISON = (
    "Plasmodium falciparum 3D7",
    "Plasmodium falciparum Dd2",
    "Plasmodium falciparum 7G8",
    "Plasmodium falciparum HB3",
    "Plasmodium falciparum GB4",
    "Plasmodium falciparum IT",
    "Plasmodium vivax P01",
    "Plasmodium knowlesi strain H",
)
_SETTLED = {"confirmed", "failed", "unreached", "unsampled"}


@pytest.fixture(autouse=True)
def observed(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    set_observer(PathfinderObserver())
    try:
        with sealed_provider_keys(monkeypatch):
            yield
    finally:
        set_observer(NoObserver())


async def _run(
    connector: InMemoryConnector, site_id: str, scope: AuditScope
) -> tuple[UUID, AuditOutcome]:
    owner = await seed_thread(site_id)
    run_id = await create_run(owner=owner, scope=scope)
    await start_run(run_id, owner)
    while waiting := queued(connector):
        (job,) = waiting
        due = job["scheduled_at"]
        if due is not None:
            await asyncio.sleep(max(0.0, (due - datetime.now(UTC)).total_seconds()))
        await work(connector, job)
    return run_id, await outcome(run_id, owner)


@pytest.mark.usefixtures("db_cleaner", "patch_app_db_engine")
async def test_the_recorded_positives_are_confirmed_on_qa(
    require_wdk_creds: str, in_memory_jobs: InMemoryConnector
) -> None:
    token = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        plasmo = AuditScope(
            site_id="plasmodb",
            targets=(
                GenePairTarget(
                    check="pseudogene_call",
                    genes=("PfNF54_100037200:pseudogene", PIGA),
                ),
            ),
        )
        run_id, done = await _run(in_memory_jobs, "plasmodb", plasmo)
        assert (done.status, done.requests > 0) == ("finished", True)
        async with async_session_factory() as session:
            (piga,) = await AuditFindingRepository(session).findings(
                run_id, FindingFilter()
            )
        assert (piga.status, piga.error_type) == (
            "confirmed",
            "intact_gene_called_pseudogene",
        )

        toxo = AuditScope(
            site_id="toxodb",
            targets=(
                GenePairTarget(check="selenoprotein_end", genes=(GT1_SELK, ME49_SELK)),
            ),
        )
        run_id, _ = await _run(in_memory_jobs, "toxodb", toxo)
        async with async_session_factory() as session:
            (selk,) = await AuditFindingRepository(session).findings(
                run_id, FindingFilter()
            )
        assert (selk.status, selk.error_type) == ("confirmed", "sec_read_as_stop")
    finally:
        veupathdb_auth_token_ctx.reset(token)


@pytest.mark.usefixtures("db_cleaner", "patch_app_db_engine")
async def test_one_genome_is_screened_and_confirmed_on_qa(
    require_wdk_creds: str, in_memory_jobs: InMemoryConnector
) -> None:
    token = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        scope = AuditScope(
            site_id="plasmodb",
            genomes=(NF54,),
            comparison=COMPARISON,
            checks=("gene_length", "gene_split"),
            confirm_limit=2,
        )
        run_id, done = await _run(in_memory_jobs, "plasmodb", scope)
        async with async_session_factory() as session:
            states = await AuditRepository(session).genome_states(run_id)
            found = await AuditFindingRepository(session).findings(
                run_id, FindingFilter()
            )
        assert (done.status, done.unfinished) == ("finished", ())
        assert done.requests > 9
        assert sorted(s.status for s in states) == ["collected"] * 9
        assert {f.status for f in found} <= _SETTLED
        assert sum(f.sampled for f in found) <= 4
    finally:
        veupathdb_auth_token_ctx.reset(token)
