"""Strain targets reported apart from the sampled rates, each pair counted in both genomes it judged."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from assistant_core.platform.db import async_session_factory
from veupathdb_mcp.audit import SideVerdict, StrainModelAudit

from pathfinder.domain.audit.rates import TargetTally
from pathfinder.domain.audit.scope import AuditScope, GenePairTarget
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    NewFinding,
)
from pathfinder.services.audit import checks, confirm, screen
from pathfinder.services.audit.runs import create_run, owned_run
from pathfinder.services.audit.views import run_view
from pathfinder.tests._support.audit import (
    P3D7,
    FakeSite,
    RecordedLane,
    carried,
    gene_row,
    observed_requests,
    seed_thread,
)
from pathfinder.tests._support.audit_answers import PCYB_PKAC, strain
from pathfinder.tests.integration.services._audit_confirm import findings_of
from pathfinder.tests.integration.services._audit_stages import faked_site

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

DD2 = "Plasmodium falciparum Dd2"
SIDES: dict[str, SideVerdict] = {
    "PfDd2_S1": "STRAIN_SHORT",
    "PfDd2_S2": "UNCLEAR",
    "PfDd2_S3": "REFERENCE_LONG",
    "PfDd2_S4": "REFERENCE_LONG",
}
PAIRS = tuple(
    GenePairTarget(check="strain_model", genes=(gene, f"PF3D7_R{k}"))
    for k, gene in enumerate(SIDES, start=1)
)


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSite]:
    async def strain_model(
        site_id: str, strain_gene: str, reference_gene: str
    ) -> StrainModelAudit:
        del site_id, reference_gene
        return strain(SIDES[strain_gene])

    with observed_requests():
        fake = faked_site(monkeypatch)
        fake.rows = [
            *(gene_row(gene, DD2, 280) for gene in SIDES),
            *(gene_row(pair.genes[1], P3D7, 341) for pair in PAIRS),
            gene_row(PCYB_PKAC, P3D7, 341),
        ]
        monkeypatch.setattr(confirm, "record_rows", fake.named_rows)
        monkeypatch.setattr(checks, "audit_strain_model", strain_model)
        yield fake


async def test_each_strain_pair_counts_in_both_genomes_and_its_error_where_it_lives(
    site: FakeSite,
) -> None:
    del site
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=PAIRS)
    )
    for stage in (screen.run_screen_stage, confirm.run_confirm_stage):
        await carried(
            stage, await owned_run(run_id, owner), RecordedLane(), seconds=3600
        )

    found = await findings_of(run_id)
    assert {
        gene: (f.screened_genome, f.paired_genome, f.genome, f.error_type)
        for gene, f in found.items()
    } == {
        "PfDd2_S1": (DD2, P3D7, DD2, "truncated_model"),
        "PfDd2_S2": (DD2, P3D7, DD2, None),
        "PfDd2_S3": (DD2, P3D7, P3D7, "over_extended_model"),
        "PfDd2_S4": (DD2, P3D7, P3D7, "over_extended_model"),
    }
    view = await run_view(run_id, owner.user_id)
    assert view.rates == []
    assert view.targets.genomes == [
        TargetTally(
            genome=P3D7,
            check="strain_model",
            checked=4,
            errors=2,
            unjudged=0,
            unresolved=0,
        ),
        TargetTally(
            genome=DD2,
            check="strain_model",
            checked=4,
            errors=1,
            unjudged=0,
            unresolved=0,
        ),
    ]
    assert view.targets.unplaced == 0


async def test_a_strain_pair_placed_by_the_confirm_stage_records_both_genomes(
    site: FakeSite,
) -> None:
    del site
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=PAIRS[:1])
    )
    async with async_session_factory() as session:
        await AuditFindingRepository(session).add_findings(
            run_id,
            [
                NewFinding(
                    genome="",
                    target=PAIRS[0],
                    sampled=True,
                    status="unreached",
                    message="plasmodb did not answer",
                )
            ],
        )
        await session.commit()
    await carried(
        confirm.run_confirm_stage,
        await owned_run(run_id, owner),
        RecordedLane(),
        seconds=3600,
    )
    (finding,) = (await findings_of(run_id)).values()
    assert (finding.screened_genome, finding.paired_genome, finding.genome) == (
        DD2,
        P3D7,
        DD2,
    )
