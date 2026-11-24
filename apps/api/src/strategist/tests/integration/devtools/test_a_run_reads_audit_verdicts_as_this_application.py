from __future__ import annotations

import pytest
from assistant_core.platform.context import DEFAULT_APPLICATION_ID, application_id_ctx

from strategist.devtools.eval_runner import CaseThreads, stored_verdicts
from strategist.domain.audit.verdicts import GeneModelVerdict, read_cite
from strategist.services.audit.verdicts import AuditCaller, record_verdict
from strategist.tests._support.audit import seed_thread

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

_VERDICT = GeneModelVerdict(
    genes=("EXA_0001", "EXR_0001"),
    model_genome="Examplea alpha A",
    verdict="error",
    error_type="intact_gene_called_pseudogene",
    certainty="high",
    cause="The strain gene keeps the reading frame its reference gene has.",
    cites=(read_cite("audit_pseudogene_call", "EXA_0001", "EXR_0001"),),
)


async def test_a_run_outside_a_request_reads_the_verdicts_its_thread_wrote() -> None:
    owner = await seed_thread()
    await record_verdict(
        caller=AuditCaller(
            user_id=owner.user_id,
            conversation_id=owner.conversation_id,
            site_id="plasmodb",
        ),
        origin="auditor",
        verdict=_VERDICT,
        model_id="test:auditor",
    )
    threads = CaseThreads(
        conversation_ids=[owner.conversation_id], user_id=owner.user_id
    )

    reset = application_id_ctx.set(DEFAULT_APPLICATION_ID)
    try:
        verdicts = await stored_verdicts(threads)
    finally:
        application_id_ctx.reset(reset)

    assert {gene: v.verdict for gene, v in verdicts.items()} == {
        "EXA_0001": "error",
        "EXR_0001": "error",
    }
