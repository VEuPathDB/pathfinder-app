from __future__ import annotations

from uuid import UUID

import pytest
from assistant_core.platform.db import async_session_factory
from fastapi import FastAPI

from pathfinder.domain.audit.findings import Certainty, ErrorType
from pathfinder.domain.audit.scope import (
    AuditScope,
    CheckName,
    GenePairTarget,
    GeneTarget,
    SingleGeneTarget,
)
from pathfinder.domain.audit.verdicts import (
    FindingReview,
    GeneModelVerdict,
    VerdictKind,
    finding_cite,
)
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    NewFinding,
    SettledFinding,
)
from pathfinder.persistence.repositories.audit_reviews import AuditReviewRepository
from pathfinder.services.audit.runs import RunOwner, create_run
from pathfinder.tests._support.audit import NF54, P3D7, seed_thread
from pathfinder.tests.integration.http.conftest import client_for

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "site_login_names_the_user"
)

_KINASE = GenePairTarget(check="selenoprotein_end", genes=("KINASE", "REF_A"))
_YIP1 = SingleGeneTarget(check="gene_length", genes=("YIP1",))
_KEPT = SingleGeneTarget(check="gene_length", genes=("KEPT",))
_MOVED = GenePairTarget(check="pseudogene_call", genes=("MOVED", "REF_B"))


def _settled(error: ErrorType, *, genome: str | None = None) -> SettledFinding:
    return SettledFinding(
        status="confirmed", error_type=error, certainty="high", genome=genome
    )


async def _review(
    run_id: UUID,
    finding_id: int,
    verdict: VerdictKind,
    error: ErrorType | None,
    certainty: Certainty | None,
) -> None:
    review = FindingReview(
        verdict=GeneModelVerdict(
            genes=("GENE",),
            model_genome=NF54,
            verdict=verdict,
            error_type=error,
            certainty=certainty,
            cause="The sample cause.",
            cites=(finding_cite(finding_id),),
        ),
        already_known="not_searched",
        card_text="The sample fix.",
    )
    async with async_session_factory() as session:
        await AuditReviewRepository(session).add_review(
            run_id=run_id, finding_id=finding_id, review=review, model_id="sample"
        )
        await session.commit()


async def _reviewed_run() -> tuple[RunOwner, UUID, dict[str, int]]:
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner,
        scope=AuditScope(
            site_id="plasmodb",
            genomes=(NF54,),
            checks=("gene_length",),
            targets=(_KINASE, _YIP1, _KEPT, _MOVED),
        ),
    )
    settled: dict[str, tuple[GeneTarget, SettledFinding]] = {
        "kinase": (_KINASE, _settled("sec_read_as_stop")),
        "yip1": (_YIP1, _settled("truncated_model")),
        "kept": (_KEPT, _settled("truncated_model")),
        "moved": (_MOVED, _settled("intact_gene_called_pseudogene", genome=P3D7)),
    }
    ids: dict[str, int] = {}
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(genome=NF54, target=target, sampled=True, status="screened")
                for target in (_KINASE, _YIP1, _KEPT, _MOVED)
            ],
        )
        for name, (target, outcome) in settled.items():
            (found,) = await repo.findings(run_id, FindingFilter(keys=(target.key,)))
            await repo.try_finding(found.id)
            await repo.settle_finding(found.id, outcome)
            ids[name] = found.id
        await session.commit()
    await _review(run_id, ids["kinase"], "error", "split_model", "medium")
    await _review(run_id, ids["yip1"], "no_error", None, None)
    return owner, run_id, ids


async def _listed(client_args: tuple[FastAPI, RunOwner, UUID], error: str) -> list[int]:
    app, owner, run_id = client_args
    async with client_for(app, owner.user_id) as client:
        page = (
            await client.get(
                f"/api/v1/audits/{run_id}/findings", params={"errorType": error}
            )
        ).json()
    assert page["total"] == len(page["findings"])
    return [finding["id"] for finding in page["findings"]]


async def test_the_sections_and_the_error_filter_name_the_same_findings(
    app: FastAPI,
) -> None:
    owner, run_id, ids = await _reviewed_run()
    async with client_for(app, owner.user_id) as client:
        view = (await client.get(f"/api/v1/audits/{run_id}")).json()
    sections = {
        section["errorType"]: section["count"] for section in view["errorTypes"]
    }
    assert sections == {
        "intact_gene_called_pseudogene": 1,
        "truncated_model": 1,
        "split_model": 1,
    }
    args = (app, owner, run_id)
    assert await _listed(args, "split_model") == [ids["kinase"]]
    assert await _listed(args, "truncated_model") == [ids["kept"]]
    assert await _listed(args, "sec_read_as_stop") == []


async def test_a_section_names_the_checks_of_its_findings(app: FastAPI) -> None:
    owner, run_id, _ = await _reviewed_run()
    async with client_for(app, owner.user_id) as client:
        view = (await client.get(f"/api/v1/audits/{run_id}")).json()
    checks: dict[str, list[CheckName]] = {
        section["errorType"]: section["checks"] for section in view["errorTypes"]
    }
    assert checks == {
        "intact_gene_called_pseudogene": ["pseudogene_call"],
        "truncated_model": ["gene_length"],
        "split_model": ["selenoprotein_end"],
    }


async def test_a_retyped_finding_reads_as_the_review_named_it(app: FastAPI) -> None:
    owner, run_id, ids = await _reviewed_run()
    async with client_for(app, owner.user_id) as client:
        detail = (
            await client.get(f"/api/v1/audits/{run_id}/findings/{ids['kinase']}")
        ).json()
        rejected = (
            await client.get(f"/api/v1/audits/{run_id}/findings/{ids['yip1']}")
        ).json()
    assert detail["finding"]["errorType"] == "sec_read_as_stop"
    assert detail["finding"]["effectiveErrorTitle"] == "One gene split into two models"
    assert rejected["finding"]["effectiveErrorTitle"] == "Model too short"


async def test_the_sample_counts_read_by_the_screened_genome_without_targets(
    app: FastAPI,
) -> None:
    owner = await seed_thread()
    sampled = SingleGeneTarget(check="gene_length", genes=("SAMPLED",))
    chosen = SingleGeneTarget(check="gene_length", genes=("CHOSEN",))
    run_id = await create_run(
        owner=owner,
        scope=AuditScope(
            site_id="plasmodb",
            genomes=(NF54,),
            checks=("gene_length",),
            targets=(chosen,),
        ),
    )
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(genome=NF54, target=target, sampled=True, status="screened")
                for target in (sampled, chosen)
            ],
        )
        for target in (sampled, chosen):
            (found,) = await repo.findings(run_id, FindingFilter(keys=(target.key,)))
            await repo.try_finding(found.id)
            await repo.settle_finding(
                found.id, _settled("truncated_model", genome=P3D7)
            )
        await session.commit()
    async with client_for(app, owner.user_id) as client:
        view = (await client.get(f"/api/v1/audits/{run_id}")).json()
    assert [
        (row["genome"], row["modelGenome"], row["errorType"], row["count"])
        for row in view["sampleCounts"]
    ] == [(NF54, P3D7, "truncated_model", 1)]
    assert [
        (rate["genome"], rate["bounds"]["confirmed"], rate["bounds"]["checked"])
        for rate in view["rates"]
    ] == [(NF54, 0, 1)]
