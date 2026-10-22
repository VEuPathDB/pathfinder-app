"""A finding the check could not judge stays out of its genome's rate and is counted beside it."""

from __future__ import annotations

import pytest
from assistant_core.platform.db import async_session_factory
from veupathdb_mcp.audit import rate_with_bounds

from pathfinder.domain.audit.findings import counts_of
from pathfinder.domain.audit.scope import AuditScope, SingleGeneTarget
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
    NewFinding,
    SettledFinding,
)
from pathfinder.persistence.repositories.audit_tallies import AuditTallyRepository
from pathfinder.persistence.repositories.audit_weighings import AuditWeighingRepository
from pathfinder.services.audit.runs import create_run
from pathfinder.services.audit.views import run_view
from pathfinder.tests._support.audit import NF54, seed_thread

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

VIVAX = "Plasmodium vivax P01"

GAP = (
    "GAP: the absent genome has an assembly gap at the locus, so the check "
    "cannot judge whether its DNA holds the gene"
)
_SETTLED = [
    SettledFinding(status="confirmed", error_type="truncated_model", certainty="high"),
    SettledFinding(status="confirmed"),
    SettledFinding(status="confirmed", message=GAP, judged=False),
    SettledFinding(status="confirmed", message=GAP, judged=False),
    SettledFinding(status="failed", message="the record holds no protein"),
]


async def test_a_rate_counts_only_judged_findings_and_names_the_rest() -> None:
    owner = await seed_thread()
    targets = tuple(
        SingleGeneTarget(check="gene_length", genes=(f"NF54_G{k}",))
        for k in range(len(_SETTLED))
    )
    scope = AuditScope(site_id="plasmodb", genomes=(NF54,), checks=("gene_length",))
    run_id = await create_run(owner=owner, scope=scope)
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(genome=NF54, target=t, sampled=True, status="screened")
                for t in targets
            ],
        )
        found = await repo.findings(run_id, FindingFilter())
        for finding, settled in zip(found, _SETTLED, strict=True):
            await repo.try_finding(finding.id)
            await repo.settle_finding(finding.id, settled)
        await session.commit()
        tally = await AuditTallyRepository(session).tally(run_id)

    assert [(t.status, t.error_type, t.judged, t.count) for t in tally] == [
        ("confirmed", "truncated_model", True, 1),
        ("confirmed", None, False, 2),
        ("confirmed", None, True, 1),
        ("failed", None, True, 1),
    ]
    view = await run_view(run_id, owner.user_id)
    (rate,) = view.rates
    assert (rate.genome, rate.check, rate.unjudged, rate.unresolved) == (
        NF54,
        "gene_length",
        2,
        1,
    )
    assert rate.bounds == rate_with_bounds(1, 2, 1)
    assert view.targets.genomes == []
    assert counts_of(view.counts).unjudged == 2


async def test_an_error_the_relatives_moved_is_clean_in_the_genome_that_screened_it() -> (
    None
):
    owner = await seed_thread()
    targets = [
        SingleGeneTarget(check="gene_length", genes=(f"NF54_G{k}",)) for k in range(10)
    ]
    scope = AuditScope(site_id="plasmodb", genomes=(NF54,), checks=("gene_length",))
    run_id = await create_run(owner=owner, scope=scope)
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(genome=NF54, target=t, sampled=True, status="screened")
                for t in targets
            ],
        )
        found = await repo.findings(run_id, FindingFilter())
        for k, finding in enumerate(found):
            named = k < 4
            await repo.try_finding(finding.id)
            await repo.settle_finding(
                finding.id,
                SettledFinding(
                    status="confirmed",
                    error_type="truncated_model" if named else None,
                    certainty="high" if named else None,
                ),
            )
        await AuditWeighingRepository(session).remodel(
            found[3].id, "over_extended_model", "medium", VIVAX
        )
        await session.commit()
    (rate,) = (await run_view(run_id, owner.user_id)).rates
    assert (rate.genome, rate.bounds) == (NF54, rate_with_bounds(3, 10, 0))
    assert rate.bounds is not None
    assert (round(rate.bounds.low, 3), round(rate.bounds.high, 3)) == (0.108, 0.603)
