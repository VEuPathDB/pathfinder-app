"""A finding read from its routes names the verdict its check gave and whether it is a gene target."""

from __future__ import annotations

from uuid import UUID

import pytest
from assistant_core.platform.db import async_session_factory
from fastapi import FastAPI
from sqlalchemy import text

from pathfinder.domain.audit.confirmations import (
    Confirmation,
    IntronConfirmation,
    StrainConfirmation,
)
from pathfinder.domain.audit.findings import ConfirmationEvidence, GeneEvidencePayload
from pathfinder.domain.audit.scope import (
    AuditScope,
    GenePairTarget,
    GeneTarget,
    SingleGeneTarget,
)
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    NewFinding,
    SettledFinding,
)
from pathfinder.services.audit.runs import RunOwner, create_run
from pathfinder.tests._support.audit import NF54_PIGA, PIGA, seed_thread
from pathfinder.tests._support.audit_answers import (
    PCYB_PKAC,
    PCYM_PKAC,
    PKAC_INTRONS,
    strain,
)
from pathfinder.tests._support.audit_evidence import K13, PIGA_EVIDENCE, evidence_of
from pathfinder.tests.integration.http._audit_reads import (
    PIGA_ALIAS,
    aliased_pair_run,
    mixed_run,
    screened_genome_run,
    stored_intron_run,
    stored_pair_run,
)
from pathfinder.tests.integration.http.conftest import client_for

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "site_login_names_the_user"
)
GENE_PAGE = "https://qa.plasmodb.org/plasmo.qa/app/record/gene/"
STRAIN_M = "Plasmodium cynomolgi strain M"
PKAC_INTRON = SingleGeneTarget(check="intron_support", genes=(PCYM_PKAC,))
PKAC_STRAIN = GenePairTarget(check="strain_model", genes=(PCYM_PKAC, PCYB_PKAC))
_UNMODELLED = text(
    "UPDATE audit_evidence SET payload = payload "
    "#- '{confirmation,result,models}' #- '{confirmation,result,evidenceUnread}' "
    "WHERE finding_id = :finding_id"
)


async def _stored(
    target: GeneTarget, confirmation: Confirmation
) -> tuple[RunOwner, UUID, int]:
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=(target,))
    )
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(
                    genome=STRAIN_M, target=target, sampled=True, status="screened"
                )
            ],
        )
        (finding,) = await repo.findings(run_id, FindingFilter())
        await repo.try_finding(finding.id)
        await repo.settle_finding(
            finding.id,
            SettledFinding(
                status="confirmed", error_type="missing_exon", certainty="high"
            ),
        )
        await repo.try_evidence(finding.id, "confirmation")
        await repo.save_evidence(
            finding.id, ConfirmationEvidence(confirmation=confirmation), requests=1
        )
        await session.commit()
    return owner, run_id, finding.id


async def test_a_finding_names_its_verdict_and_where_it_came_from(
    app: FastAPI,
) -> None:
    owner, run_id, pair_id = await stored_pair_run()
    screened_owner, screened_run = await screened_genome_run()
    async with client_for(app, owner.user_id) as client:
        page = (await client.get(f"/api/v1/audits/{run_id}/findings")).json()
        detail = (
            await client.get(f"/api/v1/audits/{run_id}/findings/{pair_id}")
        ).json()
    async with client_for(app, screened_owner.user_id) as client:
        screened = (await client.get(f"/api/v1/audits/{screened_run}/findings")).json()
    assert [(f["id"], f["verdict"], f["fromTarget"]) for f in page["findings"]] == [
        (pair_id, "INTACT", True),
        (pair_id + 1, None, True),
    ]
    assert (detail["finding"]["verdict"], detail["finding"]["fromTarget"]) == (
        "INTACT",
        True,
    )
    assert [
        (f["verdictText"], f["checkTitle"], f["errorTitle"]) for f in page["findings"]
    ] == [
        (
            "The strain's DNA encodes the whole protein, so the pseudogene call is wrong",
            "Pseudogene calls on intact genes",
            "Intact gene called a pseudogene",
        ),
        (None, "Gene length against orthologs", None),
    ]
    assert [group["kind"] for group in detail["facts"]] == ["confirmation"]
    assert detail["models"] is None
    assert detail["facts"][0]["facts"][0] == {
        "label": "Reference coding sequence",
        "value": "1,386 bases",
    }
    assert [(f["verdict"], f["fromTarget"]) for f in screened["findings"]] == [
        (None, False),
        (None, False),
    ]


async def test_an_intron_finding_reads_with_its_verdict(app: FastAPI) -> None:
    owner, run_id, finding_id = await stored_intron_run()
    async with client_for(app, owner.user_id) as client:
        page = (await client.get(f"/api/v1/audits/{run_id}/findings")).json()
    assert [
        (f["id"], f["check"], f["verdict"], f["errorType"]) for f in page["findings"]
    ] == [(finding_id, "intron_support", "UNSUPPORTED_MISSING_EXON", "missing_exon")]


async def test_findings_filter_by_certainty_and_by_target(app: FastAPI) -> None:
    owner, run_id, ids = await mixed_run()
    url = f"/api/v1/audits/{run_id}/findings"
    async with client_for(app, owner.user_id) as client:
        medium = (await client.get(url, params={"certainty": "medium"})).json()
        targets = (await client.get(url, params={"target": "true"})).json()
        screened = (await client.get(url, params={"target": "false"})).json()
        refused = await client.get(url, params={"certainty": "certain"})
    assert ([f["id"] for f in medium["findings"]], medium["total"]) == (
        [ids["split"]],
        1,
    )
    assert ([f["id"] for f in targets["findings"]], targets["total"]) == (
        [ids["target"]],
        1,
    )
    assert (sorted(f["id"] for f in screened["findings"]), screened["total"]) == (
        sorted([ids["short"], ids["split"]]),
        2,
    )
    assert refused.status_code == 422


async def test_a_run_with_no_gene_target_lists_no_target_finding(
    app: FastAPI,
) -> None:
    owner, run_id = await screened_genome_run()
    async with client_for(app, owner.user_id) as client:
        page = (
            await client.get(
                f"/api/v1/audits/{run_id}/findings", params={"target": "true"}
            )
        ).json()
    assert (page["findings"], page["total"]) == ([], 0)


async def test_a_finding_links_its_genes_to_the_site(app: FastAPI) -> None:
    owner, run_id, pair_id = await stored_pair_run()
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.try_evidence(pair_id, "gene_evidence")
        await repo.save_evidence(
            pair_id,
            GeneEvidencePayload(
                genes=(PIGA, K13), evidence=(PIGA_EVIDENCE, evidence_of(K13))
            ),
            requests=2,
        )
        await session.commit()
    async with client_for(app, owner.user_id) as client:
        page = (await client.get(f"/api/v1/audits/{run_id}/findings")).json()
        detail = (
            await client.get(f"/api/v1/audits/{run_id}/findings/{pair_id}")
        ).json()
    assert [f["genes"] for f in page["findings"]] == [
        [
            {"gene": NF54_PIGA, "url": GENE_PAGE + NF54_PIGA},
            {"gene": PIGA, "url": GENE_PAGE + PIGA},
        ],
        [{"gene": "NF54_SHORT", "url": GENE_PAGE + "NF54_SHORT"}],
    ]
    assert detail["finding"]["genes"] == page["findings"][0]["genes"]
    assert detail["genes"] == [
        *page["findings"][0]["genes"],
        {"gene": K13, "url": GENE_PAGE + K13},
    ]


async def test_a_finding_links_the_genes_its_confirmation_resolved(
    app: FastAPI,
) -> None:
    owner, run_id, pair_id = await aliased_pair_run()
    async with client_for(app, owner.user_id) as client:
        page = (await client.get(f"/api/v1/audits/{run_id}/findings")).json()
        detail = (
            await client.get(f"/api/v1/audits/{run_id}/findings/{pair_id}")
        ).json()
    resolved = [
        {"gene": NF54_PIGA, "url": GENE_PAGE + NF54_PIGA},
        {"gene": PIGA, "url": GENE_PAGE + PIGA},
    ]
    (finding,) = page["findings"]
    assert finding["target"]["genes"] == [NF54_PIGA, PIGA_ALIAS]
    assert finding["genes"] == resolved
    assert detail["finding"]["genes"] == resolved
    assert detail["genes"] == resolved


async def test_an_intron_finding_reads_its_annotated_and_proposed_models(
    app: FastAPI,
) -> None:
    owner, run_id, finding_id = await _stored(
        PKAC_INTRON, IntronConfirmation(result=PKAC_INTRONS)
    )
    async with client_for(app, owner.user_id) as client:
        detail = (
            await client.get(f"/api/v1/audits/{run_id}/findings/{finding_id}")
        ).json()
    models = detail["models"]
    assert (models["kind"], models["merged"], models["stop"]) == ("intron", None, None)
    assert [(m["gene"], m["seqid"], m["strand"]) for m in models["annotated"]] == [
        (PCYM_PKAC, "PcyM_07", "+")
    ]
    assert models["proposed"]["cds"][1] == [1381887, 1382044]
    assert (
        models["proposed"]["kind"],
        models["proposed"]["removedIntrons"],
        models["proposed"]["junctionReads"],
        models["proposed"]["frameKept"],
    ) == ("corrected", [[1381746, 1382305]], [1436, 1686], True)


async def test_a_confirmation_stored_before_the_models_reads_with_no_models(
    app: FastAPI,
) -> None:
    owner, run_id, finding_id = await _stored(
        PKAC_STRAIN, StrainConfirmation(result=strain("STRAIN_SHORT"))
    )
    url = f"/api/v1/audits/{run_id}/findings/{finding_id}"
    async with client_for(app, owner.user_id) as client:
        modelled = (await client.get(url)).json()
        async with async_session_factory() as session:
            await session.execute(_UNMODELLED, {"finding_id": finding_id})
            await session.commit()
        response = await client.get(url)
    detail = response.json()
    assert [m["gene"] for m in modelled["models"]["annotated"]] == [
        PCYM_PKAC,
        PCYB_PKAC,
    ]
    assert (response.status_code, detail["models"]) == (200, None)
    assert detail["facts"] == modelled["facts"]
    assert detail["evidence"][0]["payload"]["confirmation"]["result"]["models"] == []
