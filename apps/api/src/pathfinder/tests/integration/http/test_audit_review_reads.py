from __future__ import annotations

from uuid import UUID

import pytest
from assistant_core.platform.db import async_session_factory
from fastapi import FastAPI

from pathfinder.domain.audit.findings import Certainty, ErrorType
from pathfinder.domain.audit.rates import GenomeUse, Importance, Weighing
from pathfinder.domain.audit.scope import AuditScope, SingleGeneTarget
from pathfinder.domain.audit.verdicts import (
    ErrorTypeSection,
    FindingReview,
    GeneModelVerdict,
    ReviewAgreement,
    ReviewProgress,
    StoredSynthesis,
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
from pathfinder.persistence.repositories.audit_weighings import (
    AuditWeighingRepository,
)
from pathfinder.services.audit.runs import RunOwner, create_run
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests.integration.http.conftest import client_for

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "site_login_names_the_user"
)

_GENOME = "Examplea alpha A"
_ORGANELLE_GENOME = "Examplea beta B"
SAMPLE_CAUSE = "The strain's DNA encodes the whole protein its reference encodes."
SAMPLE_FIX = "Remove the pseudogene call and annotate the full coding sequence."
_GENES = {
    "piga": "EXA_0101",
    "yip1": "EXA_0102",
    "organelle": "EXA_0103",
    "kinase": "EXA_0104",
}
_NAMED: dict[str, tuple[str, ErrorType, Certainty]] = {
    "piga": (_GENOME, "intact_gene_called_pseudogene", "high"),
    "yip1": (_GENOME, "truncated_model", "medium"),
    "organelle": (_ORGANELLE_GENOME, "organelle_split_at_join", "low"),
    "kinase": (_GENOME, "sec_read_as_stop", "medium"),
}
_REVIEWED_AS: dict[str, tuple[ErrorType, Certainty]] = {
    **{
        name: (error_type, certainty)
        for name, (_, error_type, certainty) in _NAMED.items()
    },
    "kinase": ("split_model", "low"),
}
_SPLIT_CAUSE = "The two models are parts of one protein, in order on one strand."


def _target(name: str) -> SingleGeneTarget:
    return SingleGeneTarget(check="gene_length", genes=(_GENES[name],))


def _weighing(name: str) -> Weighing:
    genome, _, certainty = _NAMED[name]
    return Weighing(
        certainty=certainty,
        importance=Importance(genes=(_GENES[name],), source="cited"),
        use=GenomeUse(genome=genome, source="model_role", reference=True),
    )


def _review(
    finding_id: int, name: str, verdict: VerdictKind, impact: float | None
) -> FindingReview:
    genome = _NAMED[name][0]
    error_type, certainty = _REVIEWED_AS[name]
    named = verdict == "error"
    return FindingReview(
        verdict=GeneModelVerdict(
            genes=(_GENES[name],),
            model_genome=genome,
            verdict=verdict,
            error_type=error_type if named else None,
            certainty=certainty if named else None,
            cause=SAMPLE_CAUSE,
            cites=(finding_cite(finding_id),),
        ),
        already_known="not_searched",
        card_text=SAMPLE_FIX,
        impact=impact,
        impact_reason=None if impact is None else "A published screen uses it.",
        second_verdict="error",
    )


async def _named_run(owner: RunOwner) -> tuple[UUID, dict[str, int]]:
    run_id = await create_run(
        owner=owner,
        scope=AuditScope(site_id="plasmodb", targets=tuple(_target(n) for n in _GENES)),
    )
    async with async_session_factory() as session:
        findings = AuditFindingRepository(session)
        await findings.add_findings(
            run_id,
            [
                NewFinding(
                    genome=_NAMED[n][0],
                    target=_target(n),
                    sampled=True,
                    status="screened",
                )
                for n in _GENES
            ],
        )
        stored = await findings.findings(run_id, FindingFilter())
        by_gene = {record.target.genes[0]: record.id for record in stored}
        ids = {name: by_gene[gene] for name, gene in _GENES.items()}
        for name, (_, error_type, certainty) in _NAMED.items():
            await findings.try_finding(ids[name])
            await findings.settle_finding(
                ids[name],
                SettledFinding(
                    status="confirmed", error_type=error_type, certainty=certainty
                ),
            )
            await AuditWeighingRepository(session).set_impact(
                ids[name], _weighing(name)
            )
        await session.commit()
    return run_id, ids


async def reviewed_run() -> tuple[RunOwner, UUID, dict[str, int]]:
    owner = await seed_thread()
    run_id, ids = await _named_run(owner)
    async with async_session_factory() as session:
        reviews = AuditReviewRepository(session)
        await reviews.add_review(
            run_id=run_id,
            finding_id=ids["piga"],
            review=_review(ids["piga"], "piga", "error", 0.8),
            model_id="test:reviewer",
        )
        await reviews.add_review(
            run_id=run_id,
            finding_id=ids["yip1"],
            review=_review(ids["yip1"], "yip1", "no_error", None),
            model_id="test:reviewer",
        )
        await reviews.add_review(
            run_id=run_id,
            finding_id=ids["kinase"],
            review=_review(ids["kinase"], "kinase", "error", None),
            model_id="test:reviewer",
        )
        await reviews.set_synthesis(
            run_id,
            StoredSynthesis(
                sections=(
                    ErrorTypeSection(
                        error_type="intact_gene_called_pseudogene",
                        cause=SAMPLE_CAUSE,
                        confirmed_by="The strain's DNA was read against its reference.",
                        finding_ids=(ids["piga"],),
                    ),
                    ErrorTypeSection(
                        error_type="split_model",
                        cause=_SPLIT_CAUSE,
                        confirmed_by="The relatives hold one protein across both.",
                        finding_ids=(ids["kinase"],),
                    ),
                ),
                headline=(ids["piga"], ids["kinase"]),
                summary="The review kept 1 finding as an error and rejected 1.",
                agreement=ReviewAgreement(sampled=2, agreed=1),
            ),
        )
        await reviews.set_review(
            run_id, ReviewProgress(status="synthesized", done=3, total=3)
        )
        await session.commit()
    return owner, run_id, ids


async def test_the_run_reads_its_headline_and_error_type_sections(app: FastAPI) -> None:
    owner, run_id, ids = await reviewed_run()
    async with client_for(app, owner.user_id) as client:
        run = (await client.get(f"/api/v1/audits/{run_id}")).json()
        page = (await client.get(f"/api/v1/audits/{run_id}/findings")).json()
        kept = (
            await client.get(f"/api/v1/audits/{run_id}/findings/{ids['piga']}")
        ).json()
    assert [line["id"] for line in run["headline"]] == [ids["piga"], ids["kinase"]]
    (section,) = [
        t
        for t in run["errorTypes"]
        if t["errorType"] == "intact_gene_called_pseudogene"
    ]
    assert (
        section["title"],
        section["count"],
        section["certainty"],
        section["cause"],
    ) == (
        "Intact gene called a pseudogene",
        1,
        "high",
        SAMPLE_CAUSE,
    )
    assert [line["reviewedImpact"] for line in section["reviewed"]] == [0.8]
    assert run["agreement"] == {
        "sampled": 2,
        "agreed": 1,
        "share": 0.5,
        "text": "Two independent reviews agreed on 1 of 2 sampled findings (50%)",
    }
    assert (
        kept["reviewText"]["secondText"]
        == "A second, independent review: The review keeps the error"
    )
    assert run["reviewState"] == {
        "status": "synthesized",
        "text": "Reviewed and summarized",
        "done": 3,
        "total": 3,
        "message": "",
    }
    lines = {f["id"]: f["reviewLine"] for f in page["findings"]}
    assert lines[ids["piga"]]["verdictText"] == "The review keeps the error"
    assert lines[ids["yip1"]]["verdictText"] == "The review finds no error"
    assert lines[ids["organelle"]] is None
    assert (
        kept["reviewText"]["paperText"]
        == "Not checked whether a published study depends on this gene's model"
    )
    assert kept["review"]["cardText"] == SAMPLE_FIX


async def test_the_headline_and_sections_carry_whole_finding_lines(
    app: FastAPI,
) -> None:
    owner, run_id, ids = await reviewed_run()
    async with client_for(app, owner.user_id) as client:
        run = (await client.get(f"/api/v1/audits/{run_id}")).json()
        page = (await client.get(f"/api/v1/audits/{run_id}/findings")).json()

    piga = {
        "id": ids["piga"],
        "genes": [_GENES["piga"]],
        "genome": _GENOME,
        "errorType": "intact_gene_called_pseudogene",
        "errorTitle": "Intact gene called a pseudogene",
        "certainty": "high",
        "impact": _weighing("piga").impact,
        "reviewedImpact": 0.8,
    }
    kinase = {
        "id": ids["kinase"],
        "genes": [_GENES["kinase"]],
        "genome": _GENOME,
        "errorType": "split_model",
        "errorTitle": "One gene split into two models",
        "certainty": "low",
        "impact": _weighing("kinase").impact,
        "reviewedImpact": None,
    }
    assert run["headline"] == [piga, kinase]
    assert run["errorTypes"] == [
        {
            "errorType": "intact_gene_called_pseudogene",
            "title": "Intact gene called a pseudogene",
            "description": (
                "The site calls the gene a pseudogene, but the genome's DNA encodes "
                "the whole protein its reference encodes."
            ),
            "count": 1,
            "genomes": [_GENOME],
            "certainty": "high",
            "cause": SAMPLE_CAUSE,
            "confirmedBy": "The strain's DNA was read against its reference.",
            "reviewed": [piga],
        },
        {
            "errorType": "split_model",
            "title": "One gene split into two models",
            "description": (
                "Two neighbouring models are parts of one protein, in order on one "
                "strand."
            ),
            "count": 1,
            "genomes": [_GENOME],
            "certainty": "low",
            "cause": _SPLIT_CAUSE,
            "confirmedBy": "The relatives hold one protein across both.",
            "reviewed": [kinase],
        },
        {
            "errorType": "organelle_split_at_join",
            "title": "Organelle gene split at the circular join",
            "description": (
                "The organelle genome is circular but stored as a line, and the gene "
                "is cut where the line ends."
            ),
            "count": 1,
            "genomes": [_ORGANELLE_GENOME],
            "certainty": "low",
            "cause": None,
            "confirmedBy": None,
            "reviewed": [],
        },
    ]
    impacts = [f["impact"] for f in page["findings"]]
    assert impacts == sorted(impacts, reverse=True)
    assert {f["id"]: f["reviewLine"] for f in page["findings"]}[ids["piga"]] == {
        "verdict": "error",
        "verdictText": "The review keeps the error",
        "secondVerdict": "error",
        "impact": 0.8,
        "impactReason": "A published screen uses it.",
        "literature": "not_searched",
        "literatureText": "The literature was not searched",
    }


async def test_a_reviewed_run_with_no_synthesis_reads_the_stored_agreement(
    app: FastAPI,
) -> None:
    owner = await seed_thread()
    run_id, ids = await _named_run(owner)
    async with async_session_factory() as session:
        await AuditReviewRepository(session).add_review(
            run_id=run_id,
            finding_id=ids["yip1"],
            review=_review(ids["yip1"], "yip1", "no_error", None),
            model_id="test:reviewer",
        )
        await session.commit()

    async with client_for(app, owner.user_id) as client:
        run = (await client.get(f"/api/v1/audits/{run_id}")).json()

    assert run["agreement"] == {
        "sampled": 1,
        "agreed": 0,
        "share": 0.0,
        "text": "Two independent reviews agreed on 0 of 1 sampled findings (0%)",
    }
    assert (run["headline"], run["reviewState"]) == ([], None)


async def test_a_run_with_no_review_reads_no_review_words(app: FastAPI) -> None:
    owner = await seed_thread()
    run_id, ids = await _named_run(owner)

    async with client_for(app, owner.user_id) as client:
        run = (await client.get(f"/api/v1/audits/{run_id}")).json()
        page = (await client.get(f"/api/v1/audits/{run_id}/findings")).json()
        detail = (
            await client.get(f"/api/v1/audits/{run_id}/findings/{ids['piga']}")
        ).json()

    assert [
        (t["errorType"], t["cause"], t["confirmedBy"], t["reviewed"])
        for t in run["errorTypes"]
    ] == [
        ("intact_gene_called_pseudogene", None, None, []),
        ("sec_read_as_stop", None, None, []),
        ("truncated_model", None, None, []),
        ("organelle_split_at_join", None, None, []),
    ]
    assert (run["headline"], run["reviewState"], run["agreement"]) == ([], None, None)
    assert [f["reviewLine"] for f in page["findings"]] == [None, None, None, None]
    assert (detail["reviewText"], detail["finding"]["reviewLine"]) == (None, None)
