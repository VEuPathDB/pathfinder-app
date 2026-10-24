"""A check's gene model reads are counted with its other requests, on the finding and on the confirm stage."""

from __future__ import annotations

import pytest
from assistant_core.platform.db import async_session_factory

from pathfinder.domain.audit.confirmations import SelenoproteinConfirmation
from pathfinder.domain.audit.findings import ConfirmationEvidence
from pathfinder.domain.audit.scope import AuditScope, GenePairTarget
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    NewFinding,
)
from pathfinder.services.audit import confirm
from pathfinder.services.audit.runs import create_run, owned_run
from pathfinder.tests._support import audit_answers
from pathfinder.tests._support.audit import (
    GT1_SELK,
    ME49_SELK,
    RecordedLane,
    carried,
    observed_requests,
    seed_thread,
)
from pathfinder.tests._support.audit_model_wire import SELK_WIRE, served_wire
from pathfinder.tests.integration.services._audit_confirm import findings_of

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

SELK = GenePairTarget(check="selenoprotein_end", genes=(GT1_SELK, ME49_SELK))
GT1 = "Toxoplasma gondii GT1"
MODEL = ("GeneModelDump",)


async def test_the_model_reads_of_a_recorded_check_are_counted() -> None:
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="toxodb", targets=(SELK,))
    )
    async with async_session_factory() as session:
        await AuditFindingRepository(session).add_findings(
            run_id,
            [NewFinding(genome=GT1, target=SELK, sampled=True, status="screened")],
        )
        await session.commit()
    run = await owned_run(run_id, owner)

    with observed_requests(), served_wire(SELK_WIRE) as served:
        await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)

    (finding,) = (await findings_of(run.id)).values()
    async with async_session_factory() as session:
        (stored,) = await AuditFindingRepository(session).evidence(run.id, [finding.id])
        read = await AuditRepository(session).run(run.id, user_id=run.user_id)
    assert read is not None
    stage = {s.name: s for s in read.stages.stages}["confirm"]
    assert served.records[-2:] == [
        ("gene", GT1_SELK, MODEL),
        ("gene", ME49_SELK, MODEL),
    ]
    assert len(served.records) == 8
    assert (finding.status, finding.requests) == ("confirmed", 9)
    assert (stage.requests, stage.store_reads) == (9, 3)
    assert stored.payload == ConfirmationEvidence(
        confirmation=SelenoproteinConfirmation(result=audit_answers.GT1_SELK)
    )
