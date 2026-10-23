"""An intron target is confirmed in a run, and its store reads count on the confirm stage."""

from __future__ import annotations

import pytest
from assistant_core.platform.db import async_session_factory
from veupathdb import get_observer
from veupathdb_mcp.audit import IntronAudit

from pathfinder.domain.audit.scope import AuditScope, SingleGeneTarget
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
    NewFinding,
)
from pathfinder.services.audit import checks, confirm
from pathfinder.services.audit.runs import create_run, owned_run
from pathfinder.tests._support.audit import (
    RecordedLane,
    carried,
    observed_requests,
    seed_thread,
)
from pathfinder.tests._support.audit_introns import INTRON_GENE, intron_audit

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

_GENOME = "Examplea alpha A"
_TARGET = SingleGeneTarget(check="intron_support", genes=(INTRON_GENE,))
_STORE_READS = 11
_WDK_READS = 3
_REQUEST = {
    "method": "GET",
    "endpoint_group": "jbrowse",
    "site_host": "qa.toxodb.org",
    "has_auth": "true",
    "status_family": "2xx",
    "outcome": "ok",
}


async def _intron_reading_the_store(site_id: str, gene: str) -> IntronAudit:
    del site_id, gene
    for _ in range(_WDK_READS):
        get_observer().on_wdk_request(0.01, _REQUEST)
    for _ in range(_STORE_READS):
        get_observer().on_jbrowse_request(0.01, _REQUEST)
    return intron_audit("UNSUPPORTED_MISSING_EXON")


async def test_an_intron_targets_confirm_stage_stores_the_store_reads_it_made(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(checks, "audit_intron_support", _intron_reading_the_store)
    owner = await seed_thread("toxodb")
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="toxodb", targets=(_TARGET,))
    )
    async with async_session_factory() as session:
        await AuditFindingRepository(session).add_findings(
            run_id,
            [
                NewFinding(
                    genome=_GENOME, target=_TARGET, sampled=True, status="screened"
                )
            ],
        )
        await session.commit()

    with observed_requests():
        await carried(
            confirm.run_confirm_stage,
            await owned_run(run_id, owner),
            RecordedLane(),
            seconds=3600,
        )

    async with async_session_factory() as session:
        run = await AuditRepository(session).run(run_id, user_id=owner.user_id)
        (finding,) = await AuditFindingRepository(session).findings(
            run_id, FindingFilter()
        )
    assert run is not None
    assert [(s.name, s.requests, s.store_reads) for s in run.stages.stages] == [
        ("collect", 0, 0),
        ("screen", 0, 0),
        ("confirm", _WDK_READS, _STORE_READS),
        ("tie_break", 0, 0),
    ]
    assert (finding.status, finding.error_type, finding.certainty) == (
        "confirmed",
        "missing_exon",
        "high",
    )
