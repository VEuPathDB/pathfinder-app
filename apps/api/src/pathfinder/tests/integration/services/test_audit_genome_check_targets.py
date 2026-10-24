"""Fusion, strain, missing-gene and organelle targets on a real database: placed, then confirmed."""

from __future__ import annotations

import httpx
import pytest
from assistant_core.platform.db import async_session_factory
from veupathdb_mcp.audit import (
    GeneFusionAudit,
    GeneId,
    GeneRow,
    MissingGeneAudit,
    OrganelleGeneAudit,
    SideVerdict,
    StrainModelAudit,
)

from pathfinder.domain.audit.scope import (
    AuditScope,
    GenePairTarget,
    MissingGeneTarget,
    OrganelleTarget,
    SingleGeneTarget,
)
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    NewFinding,
)
from pathfinder.persistence.repositories.audit_tallies import AuditTallyRepository
from pathfinder.services.audit import checks, confirm, screen
from pathfinder.services.audit.runs import create_run, owned_run
from pathfinder.tests._support.audit import (
    NF54,
    NF54_PIGA,
    PIGA,
    FakeSite,
    RecordedLane,
    carried,
    gene_row,
    seed_thread,
)
from pathfinder.tests._support.audit_answers import (
    ARI_NAC,
    CYTB,
    FRAGILE_RPT6,
    GT1,
    NF54_MITO,
    PCYB_PKAC,
    PCYM_PKAC,
    fusion,
    missing,
    organelle,
    strain,
)
from pathfinder.tests.integration.services._audit_confirm import (
    CountedLane,
    findings_of,
    run_with,
)

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

MISSING = MissingGeneTarget(check="missing_gene", genes=(ARI_NAC,), absent_organism=GT1)
MITO = OrganelleTarget(
    check="organelle_join", genes=(CYTB,), organism=NF54, sequence_id=NF54_MITO
)
PIGA_PAIR = GenePairTarget(check="pseudogene_call", genes=(NF54_PIGA, PIGA))
STRAIN = GenePairTarget(check="strain_model", genes=(PCYM_PKAC, PCYB_PKAC))
STRAIN_M = "Plasmodium cynomolgi strain M"
STRAIN_B = "Plasmodium cynomolgi strain B"
FRAGILE = "Plasmodium fragile strain nilgiri"
FUSION = SingleGeneTarget(check="gene_fusion", genes=(FRAGILE_RPT6,))


class GeneReads:
    def __init__(self, *failures: BaseException) -> None:
        self.asked: list[list[str]] = []
        self.failures = list(failures)

    async def named_rows(self, site_id: str, gene_ids: list[str]) -> list[GeneRow]:
        del site_id
        self.asked.append(gene_ids)
        if self.failures:
            raise self.failures.pop(0)
        return [gene_row(PCYB_PKAC, STRAIN_B, 341)]


async def test_a_target_that_names_its_genome_is_placed_there_without_a_gene_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = FakeSite([])
    site.target_failures.extend([httpx.ConnectError("connection refused")] * 20)
    monkeypatch.setattr(screen, "upload_gene_list", site.upload_list)
    monkeypatch.setattr(screen, "read_gene_list", site.read_list)
    owner = await seed_thread()
    scope = AuditScope(site_id="plasmodb", targets=(MISSING, MITO, PIGA_PAIR))
    run_id = await create_run(owner=owner, scope=scope)
    await carried(
        screen.run_screen_stage,
        await owned_run(run_id, owner),
        RecordedLane(),
        seconds=10,
    )
    async with async_session_factory() as session:
        found = await AuditFindingRepository(session).findings(run_id, FindingFilter())
    assert {f.target.key: (f.genome, f.status) for f in found} == {
        MISSING.key: (GT1, "screened"),
        MITO.key: (NF54, "screened"),
        PIGA_PAIR.key: ("", "unreached"),
    }
    assert site.uploads == [[PIGA, NF54_PIGA]]


async def test_an_answer_that_names_no_error_keeps_what_its_check_could_not_judge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def missing_gene(
        site_id: str, example_gene: str, absent_organism: str
    ) -> MissingGeneAudit:
        del site_id, example_gene, absent_organism
        return missing("GAP")

    async def strain_model(
        site_id: str, strain_gene: str, reference_gene: str
    ) -> StrainModelAudit:
        del site_id, strain_gene, reference_gene
        return strain("STRAIN_SHORT")

    monkeypatch.setattr(checks, "audit_missing_gene", missing_gene)
    monkeypatch.setattr(checks, "audit_strain_model", strain_model)
    run = await run_with(
        [
            NewFinding(genome=GT1, target=MISSING, sampled=True, status="screened"),
            NewFinding(genome=STRAIN_M, target=STRAIN, sampled=True, status="screened"),
        ]
    )
    lane = CountedLane()
    await carried(confirm.run_confirm_stage, run, lane, seconds=3600)
    found = await findings_of(run.id)
    settled = {
        gene: (f.genome, f.status, f.error_type, f.certainty, f.message)
        for gene, f in found.items()
    }
    assert settled == {
        ARI_NAC: (
            GT1,
            "confirmed",
            None,
            None,
            (
                "GAP: the absent genome has an assembly gap at the locus, so the "
                "check cannot judge whether its DNA holds the gene"
            ),
        ),
        PCYM_PKAC: (STRAIN_M, "confirmed", "truncated_model", "high", None),
    }
    assert lane.updates == [
        (1, 2, "missing_gene:TGARI_257090:Toxoplasma gondii GT1: GAP"),
        (2, 2, "strain_model:PcyM_0736700+PCYB_074210: STRAIN_SHORT"),
    ]


@pytest.mark.parametrize(
    ("side", "genome", "error_type", "asked"),
    [
        ("REFERENCE_LONG", STRAIN_B, "over_extended_model", [[PCYB_PKAC]]),
        ("STRAIN_SHORT", STRAIN_M, "truncated_model", []),
    ],
)
async def test_a_strain_finding_is_settled_in_the_genome_of_the_model_called_wrong(
    monkeypatch: pytest.MonkeyPatch,
    side: SideVerdict,
    genome: str,
    error_type: str,
    asked: list[list[str]],
) -> None:
    async def strain_model(
        site_id: str, strain_gene: str, reference_gene: str
    ) -> StrainModelAudit:
        del site_id, strain_gene, reference_gene
        return strain(side)

    reads = GeneReads()
    monkeypatch.setattr(checks, "audit_strain_model", strain_model)
    monkeypatch.setattr(confirm, "record_rows", reads.named_rows)
    run = await run_with(
        [NewFinding(genome=STRAIN_M, target=STRAIN, sampled=True, status="screened")]
    )
    await carried(confirm.run_confirm_stage, run, CountedLane(), seconds=3600)
    finding = (await findings_of(run.id))[PCYM_PKAC]
    assert (finding.genome, finding.status, finding.error_type) == (
        genome,
        "confirmed",
        error_type,
    )
    assert reads.asked == asked
    async with async_session_factory() as session:
        tally = await AuditTallyRepository(session).tally(run.id)
    assert [(t.genome, t.check, t.error_type, t.count) for t in tally] == [
        (genome, "strain_model", error_type, 1)
    ]


async def test_a_reference_genome_the_site_does_not_answer_leaves_the_finding_unreached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def strain_model(
        site_id: str, strain_gene: str, reference_gene: str
    ) -> StrainModelAudit:
        del site_id, strain_gene, reference_gene
        return strain("REFERENCE_LONG")

    refused = "connection refused"
    reads = GeneReads(httpx.ConnectError(refused))
    monkeypatch.setattr(checks, "audit_strain_model", strain_model)
    monkeypatch.setattr(confirm, "record_rows", reads.named_rows)
    run = await run_with(
        [NewFinding(genome=STRAIN_M, target=STRAIN, sampled=True, status="screened")]
    )
    await carried(confirm.run_confirm_stage, run, CountedLane(), seconds=10)
    finding = (await findings_of(run.id))[PCYM_PKAC]
    assert (finding.genome, finding.status, finding.error_type, finding.message) == (
        STRAIN_M,
        "unreached",
        None,
        refused,
    )


async def test_a_fusion_missing_or_organelle_error_stays_in_the_genome_it_was_placed_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def gene_fusion(site_id: str, gene: str) -> GeneFusionAudit:
        del site_id, gene
        return fusion("EXTRA_MATCHES_NEIGHBOUR")

    async def missing_gene(
        site_id: str, example_gene: str, absent_organism: str
    ) -> MissingGeneAudit:
        del site_id, example_gene, absent_organism
        return missing("IN_DNA_UNANNOTATED")

    async def organelle_gene(
        site_id: str, organism: str, sequence_id: str, reference_gene: str
    ) -> OrganelleGeneAudit:
        del site_id, organism, sequence_id, reference_gene
        return organelle("SPLIT_AT_JOIN")

    reads = GeneReads()
    monkeypatch.setattr(checks, "audit_gene_fusion", gene_fusion)
    monkeypatch.setattr(checks, "audit_missing_gene", missing_gene)
    monkeypatch.setattr(checks, "audit_organelle_gene", organelle_gene)
    monkeypatch.setattr(confirm, "record_rows", reads.named_rows)
    run = await run_with(
        [
            NewFinding(genome=FRAGILE, target=FUSION, sampled=True, status="screened"),
            NewFinding(genome=GT1, target=MISSING, sampled=True, status="screened"),
            NewFinding(genome=NF54, target=MITO, sampled=True, status="screened"),
        ]
    )
    await carried(confirm.run_confirm_stage, run, CountedLane(), seconds=3600)
    found = await findings_of(run.id)
    assert {gene: (f.genome, f.error_type) for gene, f in found.items()} == {
        FRAGILE_RPT6: (FRAGILE, "fused_model"),
        ARI_NAC: (GT1, "missing_gene"),
        CYTB: (NF54, "organelle_split_at_join"),
    }
    assert reads.asked == []


PCYM_ALIAS = "PcyM_0736700-t26_1"
PCYB_ALIAS = "PCYB_074210-t26_1"


@pytest.mark.parametrize(
    ("side", "genome", "asked"),
    [
        ("STRAIN_SHORT", STRAIN_M, []),
        ("REFERENCE_LONG", STRAIN_B, [[PCYB_PKAC]]),
    ],
)
async def test_a_pair_given_by_alias_costs_a_read_only_for_the_reference(
    monkeypatch: pytest.MonkeyPatch,
    side: SideVerdict,
    genome: str,
    asked: list[list[str]],
) -> None:
    answer = StrainModelAudit.model_validate(
        {
            **strain(side).model_dump(),
            "gene_ids": [
                GeneId(given=PCYM_ALIAS, resolved=PCYM_PKAC),
                GeneId(given=PCYB_ALIAS, resolved=PCYB_PKAC),
            ],
        }
    )

    async def strain_model(
        site_id: str, strain_gene: str, reference_gene: str
    ) -> StrainModelAudit:
        del site_id, strain_gene, reference_gene
        return answer

    reads = GeneReads()
    monkeypatch.setattr(checks, "audit_strain_model", strain_model)
    monkeypatch.setattr(confirm, "record_rows", reads.named_rows)
    aliased = GenePairTarget(check="strain_model", genes=(PCYM_ALIAS, PCYB_ALIAS))
    run = await run_with(
        [NewFinding(genome=STRAIN_M, target=aliased, sampled=True, status="screened")]
    )
    await carried(confirm.run_confirm_stage, run, CountedLane(), seconds=3600)
    finding = (await findings_of(run.id))[PCYM_ALIAS]
    assert (finding.genome, finding.status) == (genome, "confirmed")
    assert reads.asked == asked
