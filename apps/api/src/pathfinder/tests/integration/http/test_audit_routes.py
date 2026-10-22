"""The audit read routes: a run, its findings and their evidence, for its owner only."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from assistant_core.platform.db import async_session_factory
from fastapi import FastAPI
from httpx import Response
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.audit.findings import (
    ConfirmationEvidence,
    PseudogeneConfirmation,
)
from pathfinder.domain.audit.scope import AuditScope, GenePairTarget, SingleGeneTarget
from pathfinder.persistence.repositories.audit import AuditRepository, CollectedGenome
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
    NewFinding,
    SettledFinding,
)
from pathfinder.services.audit.runs import RunOwner, create_run
from pathfinder.tests._support.audit import (
    NF54,
    NF54_PIGA,
    P3D7,
    PIGA,
    PIGA_INTACT,
    seed_thread,
)
from pathfinder.tests._support.audit_genome_screens import NF135, NF135_PRIORITY
from pathfinder.tests.integration.http.conftest import (
    client_for,
    make_user,
    other_application_client_for,
)

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "site_login_names_the_user"
)

PAIR = GenePairTarget(check="pseudogene_call", genes=(NF54_PIGA, PIGA))
SHORT = SingleGeneTarget(check="gene_length", genes=("NF54_SHORT",))
DEADLINE = datetime(2026, 10, 21, 18, 0, tzinfo=UTC)
BEYOND_BIGINT = 10**19
UNREADABLE = "the gene record of NF54_SHORT is unreadable"
UNANSWERED = "plasmodb did not answer"


def _problem(response: Response) -> tuple[int, str, str]:
    return (
        response.status_code,
        response.headers["content-type"],
        response.json()["code"],
    )


async def _stored_run() -> tuple[RunOwner, UUID, int]:
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=(PAIR, SHORT))
    )
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(genome=NF54, target=PAIR, sampled=True, status="screened"),
                NewFinding(genome=NF54, target=SHORT, sampled=True, status="screened"),
            ],
        )
        pair = (
            await repo.findings(run_id, FindingFilter(checks=("pseudogene_call",)))
        )[0]
        await repo.try_finding(pair.id)
        await repo.settle_finding(
            pair.id,
            SettledFinding(
                status="confirmed",
                error_type="intact_gene_called_pseudogene",
                certainty="high",
                requests=6,
            ),
        )
        short = (await repo.findings(run_id, FindingFilter(checks=("gene_length",))))[0]
        await repo.try_finding(short.id)
        await repo.settle_finding(
            short.id, SettledFinding(status="failed", message=UNREADABLE)
        )
        await repo.try_evidence(pair.id, "confirmation")
        await repo.save_evidence(
            pair.id,
            ConfirmationEvidence(
                confirmation=PseudogeneConfirmation(result=PIGA_INTACT)
            ),
            requests=2,
        )
        await repo.try_evidence(pair.id, "relatives")
        await repo.fail_evidence(
            pair.id, "relatives", status="unreached", message=UNANSWERED, requests=1
        )
        await session.commit()
    return owner, run_id, pair.id


async def _started_genome_run() -> tuple[RunOwner, UUID]:
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner,
        scope=AuditScope(
            site_id="plasmodb",
            genomes=(NF54,),
            comparison=(P3D7,),
            checks=("gene_length",),
        ),
    )
    async with async_session_factory() as session:
        repo = AuditRepository(session)
        await repo.add_genomes(run_id, [(NF54, "audited"), (P3D7, "comparison")])
        await repo.try_genome(run_id, NF54)
        await repo.sweep_genomes(run_id)
        await repo.record_progress(
            run_id, "collect", done=1, total=2, message="waiting 30 s for plasmodb"
        )
        await repo.set_token(run_id, b"sealed")
        await repo.set_deadline(run_id, DEADLINE)
        await repo.set_status(run_id, "running")
        await session.commit()
    return owner, run_id


async def test_the_owner_lists_and_reads_a_run(app: FastAPI) -> None:
    owner, run_id, _ = await _stored_run()
    newer = await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=(SHORT,))
    )
    async with client_for(app, owner.user_id) as client:
        listed = (await client.get("/api/v1/audits")).json()
        run = (await client.get(f"/api/v1/audits/{run_id}")).json()
    assert [
        (r["id"], r["siteId"], r["status"], r["checks"], r["targets"]) for r in listed
    ] == [
        (str(newer), "plasmodb", "planned", ["gene_length"], 1),
        (
            str(run_id),
            "plasmodb",
            "planned",
            ["gene_length", "pseudogene_call"],
            2,
        ),
    ]
    assert run["unfinished"] == ["collect", "screen", "confirm", "tie_break"]
    assert run["scope"]["targets"][0] == {
        "check": "pseudogene_call",
        "genes": [NF54_PIGA, PIGA],
    }
    assert sorted(
        (c["check"], c["status"], c["errorType"], c["count"]) for c in run["counts"]
    ) == [
        ("gene_length", "failed", None, 1),
        ("pseudogene_call", "confirmed", "intact_gene_called_pseudogene", 1),
    ]
    assert run["rates"] == []
    assert run["targets"] == {
        "genomes": [
            {
                "genome": NF54,
                "check": "gene_length",
                "checked": 0,
                "errors": 0,
                "unjudged": 0,
                "unresolved": 1,
            },
            {
                "genome": NF54,
                "check": "pseudogene_call",
                "checked": 1,
                "errors": 1,
                "unjudged": 0,
                "unresolved": 0,
            },
        ],
        "unplaced": 0,
    }


async def test_a_run_carries_its_deadline_progress_and_stopped_genomes(
    app: FastAPI,
) -> None:
    owner, run_id = await _started_genome_run()
    async with client_for(app, owner.user_id) as client:
        run = (await client.get(f"/api/v1/audits/{run_id}")).json()
    assert run["stages"]["stages"][0] == {
        "name": "collect",
        "finished": False,
        "requests": 0,
        "done": 1,
        "total": 2,
        "message": "waiting 30 s for plasmodb",
    }
    assert run["stages"]["halted"] is None
    assert "sealedToken" not in run["run"]
    assert (
        run["run"]["deadlineAt"],
        run["run"]["status"],
        run["run"]["genomes"],
        run["run"]["checks"],
        run["run"]["targets"],
    ) == ("2026-10-21T18:00:00Z", "running", [NF54], ["gene_length"], 0)
    assert [
        (g["organism"], g["role"], g["status"], g["attempts"], g["stopped"])
        for g in run["genomes"]
    ] == [(NF54, "audited", "pending", 1, 1), (P3D7, "comparison", "pending", 0, 0)]


async def test_a_genome_reads_with_its_busco_gap(app: FastAPI) -> None:
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner,
        scope=AuditScope(
            site_id="plasmodb", genomes=(NF135, NF54), checks=("gene_length",)
        ),
    )
    async with async_session_factory() as session:
        repo = AuditRepository(session)
        await repo.add_genomes(run_id, [(NF135, "audited"), (NF54, "audited")])
        await repo.try_genome(run_id, NF135)
        await repo.save_genome(
            run_id,
            CollectedGenome(
                organism=NF135, status="collected", priority=NF135_PRIORITY
            ),
        )
        await session.commit()
    async with client_for(app, owner.user_id) as client:
        run = (await client.get(f"/api/v1/audits/{run_id}")).json()
    nf135, nf54 = run["genomes"]
    assert nf135["priority"] == {
        "organism": NF135,
        "protein": {"complete": 93.0, "fragmented": 0.1, "missing": 6.9, "total": 1378},
        "genome": {"complete": 98.4, "fragmented": 0.3, "missing": 1.3, "total": 1378},
        "lineage": "aconoidasida_odb12",
        "gap": 5.4,
    }
    assert (nf54["organism"], nf54["priority"]) == (NF54, None)


async def test_findings_are_filtered_and_paged(app: FastAPI) -> None:
    owner, run_id, pair_id = await _stored_run()
    url = f"/api/v1/audits/{run_id}/findings"
    async with client_for(app, owner.user_id) as client:
        named = (
            await client.get(url, params={"errorType": "intact_gene_called_pseudogene"})
        ).json()
        first = (await client.get(url, params={"limit": 1})).json()
        second = (await client.get(url, params={"limit": 1, "offset": 1})).json()
        lengths = (await client.get(url, params={"check": "gene_length"})).json()
        refused = await client.get(url, params={"limit": 201})
        beyond = await client.get(url, params={"offset": BEYOND_BIGINT})
        misspelled = await client.get(url, params={"errorTyp": "split_model"})
        unpublished = await client.get(url, params={"error_type": "split_model"})
    assert (named["total"], [f["id"] for f in named["findings"]]) == (1, [pair_id])
    assert (first["total"], first["offset"], [f["id"] for f in first["findings"]]) == (
        2,
        0,
        [pair_id],
    )
    assert (second["offset"], [f["check"] for f in second["findings"]]) == (
        1,
        ["gene_length"],
    )
    assert [
        (f["check"], f["genome"], f["status"], f["target"]["genes"], f["message"])
        for f in lengths["findings"]
    ] == [("gene_length", NF54, "failed", ["NF54_SHORT"], UNREADABLE)]
    assert refused.status_code == 422
    assert _problem(beyond) == (422, "application/problem+json", "VALIDATION_ERROR")
    assert [_problem(r) for r in (misspelled, unpublished)] == [
        (422, "application/problem+json", "VALIDATION_ERROR"),
        (422, "application/problem+json", "VALIDATION_ERROR"),
    ]


async def test_a_finding_reads_with_its_evidence(app: FastAPI) -> None:
    owner, run_id, pair_id = await _stored_run()
    async with client_for(app, owner.user_id) as client:
        detail = (
            await client.get(f"/api/v1/audits/{run_id}/findings/{pair_id}")
        ).json()
        missing = await client.get(f"/api/v1/audits/{run_id}/findings/{pair_id + 1000}")
        beyond = await client.get(f"/api/v1/audits/{run_id}/findings/{BEYOND_BIGINT}")
    finding = detail["finding"]
    assert (
        finding["check"],
        finding["status"],
        finding["errorType"],
        finding["certainty"],
        finding["requests"],
        finding["attempts"],
        finding["stopped"],
    ) == (
        "pseudogene_call",
        "confirmed",
        "intact_gene_called_pseudogene",
        "high",
        6,
        1,
        0,
    )
    assert [
        (e["kind"], e["status"], e["requests"], e["attempts"], e["stopped"])
        for e in detail["evidence"]
    ] == [("confirmation", "stored", 2, 1, 0), ("relatives", "unreached", 1, 1, 0)]
    assert [(e["payload"] is None, e["message"]) for e in detail["evidence"]] == [
        (False, None),
        (True, UNANSWERED),
    ]
    assert (
        detail["evidence"][0]["payload"]["confirmation"]["result"]["strainCdsLength"]
        == 1386
    )
    assert missing.status_code == 404
    assert _problem(beyond) == (422, "application/problem+json", "VALIDATION_ERROR")


async def test_another_user_and_another_application_see_no_run(
    app: FastAPI, db_session: AsyncSession, other_application: str
) -> None:
    del other_application
    owner, run_id, pair_id = await _stored_run()
    stranger = await make_user(db_session)
    async with client_for(app, stranger.id) as client:
        assert (await client.get("/api/v1/audits")).json() == []
        assert (await client.get(f"/api/v1/audits/{run_id}")).status_code == 404
        assert (
            await client.get(f"/api/v1/audits/{run_id}/findings/{pair_id}")
        ).status_code == 404
    async with other_application_client_for(app, owner.user_id) as client:
        assert (await client.get("/api/v1/audits")).json() == []
        assert (await client.get(f"/api/v1/audits/{run_id}")).status_code == 404
        assert (
            await client.get(f"/api/v1/audits/{run_id}/findings")
        ).status_code == 404


async def test_an_owner_reads_no_finding_of_another_users_run(app: FastAPI) -> None:
    owner, run_id, _ = await _stored_run()
    _, other_run_id, other_pair_id = await _stored_run()
    async with client_for(app, owner.user_id) as client:
        crossed = await client.get(f"/api/v1/audits/{run_id}/findings/{other_pair_id}")
    body = crossed.json()
    assert other_run_id != run_id
    assert (crossed.status_code, body["title"], "finding" in body) == (
        404,
        "Audit finding not found",
        False,
    )
