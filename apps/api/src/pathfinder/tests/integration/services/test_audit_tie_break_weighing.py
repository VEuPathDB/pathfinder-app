"""The tie-break stage on a real database: the gene records each named finding is weighed by,
its stored impact and the inputs of it, and a length error the relatives place in the reference."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from assistant_core.platform.db import async_session_factory
from fastmcp.exceptions import ToolError
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import WDKError
from veupathdb_mcp.audit import SideVerdict

from pathfinder.domain.audit.findings import (
    ConfirmationEvidence,
    ErrorType,
    GeneEvidencePayload,
    StrainConfirmation,
)
from pathfinder.domain.audit.scope import AuditScope, GenePairTarget
from pathfinder.persistence.models import AuditRunRecord
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    NewFinding,
    SettledFinding,
)
from pathfinder.services.audit import confirm, tie_break
from pathfinder.services.audit.runs import create_run, owned_run
from pathfinder.services.audit.views import run_view
from pathfinder.tests._support.audit import (
    NF54,
    NF54_PIGA,
    RecordedLane,
    carried,
    gene_row,
    observed_requests,
    seed_thread,
)
from pathfinder.tests._support.audit_answers import PCYB_PKAC, PCYM_PKAC, strain
from pathfinder.tests._support.audit_evidence import evidence_of
from pathfinder.tests._support.veupathdb_tokens import (
    make_signing_key,
    veupathdb_token,
)
from pathfinder.tests.integration.services._audit_confirm import (
    PAIR,
    REFERENCE,
    SHORT,
    SPLIT,
    TYPICAL,
    CheckTools,
    faked_checks,
    findings_of,
    run_with,
    screened,
    weighed_of,
)

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

STRAIN = GenePairTarget(check="strain_model", genes=(PCYM_PKAC, PCYB_PKAC))
RELATIVE0 = "Plasmodium relative0 X"
REFERENCE_LONG_ROWS = [
    gene_row("NF54_SHORT", NF54, 200),
    gene_row(REFERENCE, RELATIVE0, 400),
    *(
        gene_row(f"OG7_0000001_REL{k}", f"Plasmodium relative{k} X", 205)
        for k in range(1, 6)
    ),
]


@pytest.fixture
def tools(monkeypatch: pytest.MonkeyPatch) -> Iterator[CheckTools]:
    with observed_requests():
        yield faked_checks(monkeypatch)


async def _confirmed_strain(
    side: SideVerdict, error_type: ErrorType
) -> tuple[AuditRunRecord, int]:
    run = await run_with(
        [NewFinding(genome=NF54, target=STRAIN, sampled=True, status="screened")]
    )
    (finding,) = (await findings_of(run.id)).values()
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.try_finding(finding.id)
        await repo.settle_finding(
            finding.id,
            SettledFinding(status="confirmed", error_type=error_type, certainty="high"),
        )
        await repo.save_evidence(
            finding.id,
            ConfirmationEvidence(confirmation=StrainConfirmation(result=strain(side))),
            requests=0,
        )
        await session.commit()
    return run, finding.id


async def test_a_named_finding_holds_its_genes_evidence_and_its_impact(
    tools: CheckTools,
) -> None:
    tools.uncited.add(NF54_PIGA)
    run = await run_with(screened(SHORT, TYPICAL, PAIR))
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=3600)
    read = await weighed_of(run.id, "gene_evidence")
    found = await findings_of(run.id)
    assert {gene: (e.status, e.attempts, e.requests) for gene, e in read.items()} == {
        "NF54_SHORT": ("stored", 1, 1),
        NF54_PIGA: ("stored", 1, 1),
    }
    assert read["NF54_SHORT"].payload == GeneEvidencePayload(
        genes=("NF54_SHORT",), evidence=(evidence_of("NF54_SHORT"),)
    )
    assert {gene: (f.error_type, f.impact) for gene, f in found.items()} == {
        "NF54_SHORT": ("truncated_model", 0.5),
        "NF54_TYPICAL": (None, None),
        NF54_PIGA: ("intact_gene_called_pseudogene", 0.25),
    }


async def test_a_refused_gene_evidence_read_is_failed_and_weighed_uncited(
    tools: CheckTools,
) -> None:
    refusal = "NF54_SHORT names no gene of plasmodb"
    tools.evidence_failures["NF54_SHORT"].append(ToolError(refusal))
    run = await run_with(screened(SHORT))
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=3600)
    read = (await weighed_of(run.id, "gene_evidence"))["NF54_SHORT"]
    assert (read.status, read.payload, read.attempts, read.message) == (
        "failed",
        None,
        1,
        refusal,
    )
    assert (await findings_of(run.id))["NF54_SHORT"].impact == 0.25
    assert tools.evidence_reads == ["NF54_SHORT"]


async def test_a_gene_evidence_read_answered_late_weighs_the_finding_again(
    tools: CheckTools,
) -> None:
    tools.evidence_failures["NF54_SHORT"].append(
        httpx.ConnectError("connection refused")
    )
    run = await run_with(screened(SHORT))
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=10)
    read = (await weighed_of(run.id, "gene_evidence"))["NF54_SHORT"]
    assert (read.status, read.message) == ("unreached", "connection refused")
    assert (await findings_of(run.id))["NF54_SHORT"].impact == 0.25
    await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=3600)
    read = (await weighed_of(run.id, "gene_evidence"))["NF54_SHORT"]
    assert (read.status, read.attempts) == ("stored", 2)
    assert (await findings_of(run.id))["NF54_SHORT"].impact == 0.5


@pytest.mark.parametrize(
    ("side", "error_type", "gene", "weighed"),
    [
        ("STRAIN_SHORT", "truncated_model", PCYM_PKAC, 0.5),
        ("REFERENCE_LONG", "over_extended_model", PCYB_PKAC, 1.0),
    ],
)
async def test_the_evidence_read_is_of_the_gene_whose_model_is_wrong(
    tools: CheckTools,
    side: SideVerdict,
    error_type: ErrorType,
    gene: str,
    weighed: float,
) -> None:
    run, finding_id = await _confirmed_strain(side, error_type)
    await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=3600)
    assert tools.evidence_reads == [gene]
    assert tools.ortholog_reads == []
    (read,) = (await weighed_of(run.id, "gene_evidence")).values()
    assert (read.finding_id, read.status) == (finding_id, "stored")
    (finding,) = (await findings_of(run.id)).values()
    assert finding.weighing is not None
    assert (finding.impact, finding.weighing.use.source) == (weighed, "model_role")


async def test_a_stored_gene_record_is_read_back_when_the_stage_runs_again(
    tools: CheckTools,
) -> None:
    run = await run_with(screened(SHORT))
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=3600)
    await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=3600)
    read = (await weighed_of(run.id, "gene_evidence"))["NF54_SHORT"]
    assert tools.evidence_reads == ["NF54_SHORT"]
    assert read.payload == GeneEvidencePayload(
        genes=("NF54_SHORT",), evidence=(evidence_of("NF54_SHORT"),)
    )
    assert len(evidence_of("NF54_SHORT").linkouts) == 11


async def test_a_length_error_the_relatives_place_in_the_reference_is_remodeled(
    tools: CheckTools,
) -> None:
    tools.ortholog_rows = REFERENCE_LONG_ROWS
    run = await run_with(screened(SHORT))
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=3600)
    finding = (await findings_of(run.id))["NF54_SHORT"]
    assert (
        finding.error_type,
        finding.certainty,
        finding.genome,
        finding.screened_genome,
    ) == ("over_extended_model", "medium", RELATIVE0, NF54)
    assert tools.evidence_reads == [REFERENCE]
    assert finding.weighing is not None
    assert (finding.impact, finding.weighing.importance.genes) == (0.3, (REFERENCE,))


async def test_a_remodeled_target_reports_its_error_where_it_lives(
    tools: CheckTools,
) -> None:
    tools.ortholog_rows = REFERENCE_LONG_ROWS
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=(SHORT,))
    )
    async with async_session_factory() as session:
        await AuditFindingRepository(session).add_findings(run_id, screened(SHORT))
        await session.commit()
    for stage in (confirm.run_confirm_stage, tie_break.run_tie_break_stage):
        await carried(
            stage, await owned_run(run_id, owner), RecordedLane(), seconds=3600
        )
    finding = (await findings_of(run_id))["NF54_SHORT"]
    assert (finding.genome, finding.paired_genome) == (RELATIVE0, RELATIVE0)
    report = (await run_view(run_id, owner.user_id)).targets
    assert [(t.genome, t.check, t.checked, t.errors) for t in report.genomes] == [
        (NF54, "gene_length", 1, 0),
        (RELATIVE0, "gene_length", 1, 1),
    ]


async def test_a_finding_whose_gene_was_never_read_has_the_fallback_impact(
    tools: CheckTools,
) -> None:
    tools.ortholog_failures["NF54_SHORT"].append(
        httpx.ConnectError("connection refused")
    )
    run = await run_with(screened(SHORT))
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=10)
    finding = (await findings_of(run.id))["NF54_SHORT"]
    assert finding.weighing is not None
    assert (
        finding.impact,
        finding.weighing.importance.source,
        finding.weighing.use.source,
    ) == (0.25, "not_read", "unknown")
    read = (await weighed_of(run.id, "gene_evidence"))["NF54_SHORT"]
    assert tools.evidence_reads == []
    assert (read.status, read.attempts, read.payload, read.message) == (
        "unread",
        0,
        None,
        "not read before the run's deadline",
    )


async def test_a_finding_the_deadline_left_unread_has_the_fallback_impact(
    tools: CheckTools,
) -> None:
    run = await run_with(screened(PAIR))
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=0)
    finding = (await findings_of(run.id))[NF54_PIGA]
    read = (await weighed_of(run.id, "gene_evidence"))[NF54_PIGA]
    assert (read.status, read.attempts, tools.evidence_reads) == ("unread", 0, [])
    assert finding.weighing is not None
    assert (finding.impact, finding.weighing.importance.source) == (0.25, "not_read")


async def test_a_split_model_is_weighed_by_both_its_genes(tools: CheckTools) -> None:
    run = await run_with(screened(SPLIT))
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=3600)
    (read,) = (await weighed_of(run.id, "gene_evidence")).values()
    assert sorted(tools.evidence_reads) == ["NF54_A", "NF54_B"]
    assert read.payload == GeneEvidencePayload(
        genes=SPLIT.genes, evidence=tuple(evidence_of(gene) for gene in SPLIT.genes)
    )


async def test_a_halt_reopened_tie_break_that_moves_the_error_reads_the_moved_gene(
    tools: CheckTools,
) -> None:
    refusal = WDKError("GET /record-types -> HTTP 403: refused", status=403)
    tools.ortholog_failures["NF54_SHORT"].append(refusal)
    held = veupathdb_auth_token_ctx.set(veupathdb_token(make_signing_key()))
    try:
        run = await run_with(screened(SHORT))
        await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
        await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=3600)
        refused = (await weighed_of(run.id))["NF54_SHORT"]
        assert (refused.status, tools.evidence_reads) == ("failed", ["NF54_SHORT"])
        assert refused.message is not None
        async with async_session_factory() as session:
            reopened = await AuditRepository(session).reopen_refused(
                run.id, [refused.message]
            )
            await session.commit()
        assert reopened == "tie_break"
        tools.ortholog_rows = REFERENCE_LONG_ROWS
        await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=3600)
    finally:
        veupathdb_auth_token_ctx.reset(held)
    finding = (await findings_of(run.id))["NF54_SHORT"]
    read = (await weighed_of(run.id, "gene_evidence"))["NF54_SHORT"]
    assert tools.evidence_reads == ["NF54_SHORT", REFERENCE]
    assert read.payload == GeneEvidencePayload(
        genes=(REFERENCE,), evidence=(evidence_of(REFERENCE),)
    )
    assert finding.weighing is not None
    assert (finding.error_type, finding.impact) == ("over_extended_model", 0.3)
    assert finding.weighing.importance.source == "cited"
