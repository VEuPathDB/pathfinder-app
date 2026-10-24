"""The findings pages ordered by stored impact, each finding with what it was weighed from, and a
finding read with the gene evidence the site served."""

from __future__ import annotations

from uuid import UUID

import pytest
from assistant_core.platform.db import async_session_factory
from fastapi import FastAPI

from pathfinder.domain.audit.findings import GeneEvidencePayload
from pathfinder.domain.audit.rates import Weighing
from pathfinder.domain.audit.scope import AuditScope, SingleGeneTarget
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    NewFinding,
    SettledFinding,
)
from pathfinder.persistence.repositories.audit_weighings import AuditWeighingRepository
from pathfinder.services.audit.runs import RunOwner, create_run
from pathfinder.tests._support.audit import NF54, PIGA, seed_thread
from pathfinder.tests._support.audit_evidence import (
    DMAW,
    GLO1,
    K13,
    recorded_evidence,
)
from pathfinder.tests.integration.http.conftest import client_for

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "site_login_names_the_user"
)


_WEIGHINGS = {
    0.3: ("medium", "not_read", "reference_strain"),
    1.0: ("high", "cited", "reference_strain"),
    0.075: ("low", "uncited", "other_strain"),
}


def _weighing(impact: float) -> Weighing:
    certainty, source, use = _WEIGHINGS[impact]
    return Weighing.model_validate(
        {
            "certainty": certainty,
            "importance": {"genes": ["NF54_SHORT"], "source": source},
            "use": {"genome": NF54, "source": use, "reference": use != "other_strain"},
        }
    )


async def _weighed_run(
    impacts: list[float | None],
) -> tuple[RunOwner, UUID, list[int]]:
    owner = await seed_thread()
    targets = [
        SingleGeneTarget(check="gene_length", genes=(f"NF54_SHORT{k}",))
        for k in range(len(impacts))
    ]
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=tuple(targets))
    )
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(genome=NF54, target=t, sampled=True, status="screened")
                for t in targets
            ],
        )
        ids = [f.id for f in await repo.findings(run_id, FindingFilter())]
        for finding_id, weight in zip(ids, impacts, strict=True):
            weighing = None if weight is None else _weighing(weight)
            await repo.try_finding(finding_id)
            await repo.settle_finding(
                finding_id,
                SettledFinding(
                    status="confirmed",
                    error_type="truncated_model",
                    certainty="high" if weighing is None else weighing.certainty,
                ),
            )
            if weighing is not None:
                await AuditWeighingRepository(session).set_impact(finding_id, weighing)
        await session.commit()
    return owner, run_id, ids


async def test_findings_are_paged_by_impact_across_the_run(app: FastAPI) -> None:
    owner, run_id, (unweighed, medium, high, low) = await _weighed_run(
        [None, 0.3, 1.0, 0.075]
    )
    url = f"/api/v1/audits/{run_id}/findings"
    async with client_for(app, owner.user_id) as client:
        first = (await client.get(url, params={"limit": 1})).json()
        rest = (await client.get(url, params={"offset": 1, "limit": 2})).json()
        last = (await client.get(url, params={"offset": 3})).json()
    assert [(f["id"], f["impact"]) for f in first["findings"]] == [(high, 1.0)]
    assert [(f["id"], f["impact"]) for f in rest["findings"]] == [
        (medium, 0.3),
        (low, 0.075),
    ]
    assert [(f["id"], f["impact"]) for f in last["findings"]] == [(unweighed, None)]
    assert (first["total"], rest["total"], rest["offset"]) == (4, 4, 1)
    assert [
        (f["weighing"]["importance"]["source"], f["weighing"]["use"]["source"])
        for f in rest["findings"]
    ] == [("not_read", "reference_strain"), ("uncited", "other_strain")]
    assert (
        first["findings"][0]["weighing"]["importance"]["value"],
        last["findings"][0]["weighing"],
    ) == (1.0, None)


@pytest.mark.parametrize("gene", [PIGA, K13, GLO1, DMAW])
async def test_a_finding_reads_with_the_gene_evidence_the_site_served(
    app: FastAPI, gene: str
) -> None:
    owner, run_id, (finding_id,) = await _weighed_run([1.0])
    served = recorded_evidence(gene)
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.try_evidence(finding_id, "gene_evidence")
        await repo.save_evidence(
            finding_id,
            GeneEvidencePayload(genes=(gene,), evidence=(served,)),
            requests=1,
        )
        await session.commit()
    async with client_for(app, owner.user_id) as client:
        response = await client.get(f"/api/v1/audits/{run_id}/findings/{finding_id}")
    assert response.status_code == 200
    (stored,) = response.json()["evidence"]
    assert (stored["kind"], stored["status"], stored["payload"]["genes"]) == (
        "gene_evidence",
        "stored",
        [gene],
    )
    (read,) = stored["payload"]["evidence"]
    assert (read["gene"], read["pubmed"], read["comments"], len(read["linkouts"])) == (
        gene,
        served.pubmed,
        served.comments,
        len(served.linkouts),
    )
    assert GeneEvidencePayload.model_validate(stored["payload"]).evidence == (served,)


async def test_findings_filter_by_the_genome_that_screened_them(app: FastAPI) -> None:
    owner, run_id, (kept, moved) = await _weighed_run([1.0, 0.3])
    async with async_session_factory() as session:
        await AuditWeighingRepository(session).remodel(
            moved, "over_extended_model", "medium", "Plasmodium vivax P01"
        )
        await session.commit()
    url = f"/api/v1/audits/{run_id}/findings"
    async with client_for(app, owner.user_id) as client:
        by_model = (await client.get(url, params={"genome": NF54})).json()
        screened = (
            await client.get(url, params={"screenedGenome": NF54, "sampled": "true"})
        ).json()
        unsampled = (await client.get(url, params={"sampled": "false"})).json()
    assert [f["id"] for f in by_model["findings"]] == [kept]
    assert sorted(f["id"] for f in screened["findings"]) == sorted([kept, moved])
    assert [f["screenedGenome"] for f in screened["findings"]] == [NF54, NF54]
    assert unsampled["total"] == 0
