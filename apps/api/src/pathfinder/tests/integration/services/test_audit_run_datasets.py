from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import httpx
import pytest
import respx
from assistant_core.platform.db import async_session_factory
from fastapi import FastAPI
from veupathdb import get_observer
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.wdk import get_site
from veupathdb_mcp.audit import (
    GENE_ATTRIBUTES,
    PseudogeneCallAudit,
    read_gene_list,
    upload_gene_list,
)

from pathfinder.domain.audit.scope import AuditScope, GenePairTarget
from pathfinder.domain.audit.stages import RunStages
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
    NewFinding,
)
from pathfinder.services.audit import checks, collect, confirm, screen, tie_break
from pathfinder.services.audit.runs import RunOwner, create_run, owned_run
from pathfinder.tests._support.audit import (
    NF54,
    NF54_PIGA,
    PIGA,
    PIGA_INTACT,
    RecordedLane,
    StageBody,
    carried,
    observed_requests,
    relative_organisms,
    seed_thread,
)
from pathfinder.tests.integration.http.conftest import client_for
from pathfinder.tests.integration.services._audit_confirm import faked_checks
from pathfinder.tests.integration.services._audit_stages import faked_site

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "site_login_names_the_user"
)

_USER = 376
_DATASET = 9
_STRAIN = "Plasmodium falciparum Dd2"
_REFERENCE = "Plasmodium falciparum 3D7"
_PAIRS = tuple(
    GenePairTarget(check="pseudogene_call", genes=(f"PfDd2_{k:09d}", f"PF3D7_{k:07d}"))
    for k in range(150)
)
_STAGES: tuple[StageBody, ...] = (
    collect.run_collect_stage,
    screen.run_screen_stage,
    confirm.run_confirm_stage,
    tie_break.run_tie_break_stage,
)
_STORE_READS = 7
_WDK_READS = 2
_REQUEST = {
    "method": "GET",
    "endpoint_group": "jbrowse",
    "site_host": "qa.plasmodb.org",
    "has_auth": "true",
    "status_family": "2xx",
    "outcome": "ok",
}


def _record(gene: str, organism: str) -> dict[str, object]:
    text = dict.fromkeys(GENE_ATTRIBUTES, "")
    text |= {
        "organism_full": organism,
        "protein_length": "314",
        "sequence_id": "chr14",
        "gene_start_min": "2941398",
        "gene_end_max": "2945279",
        "strand_plus_minus": "-",
        "is_pseudo": "No",
        "gene_type": "protein coding gene",
    }
    return {
        "displayName": gene,
        "id": [
            {"name": "gene_source_id", "value": gene},
            {"name": "source_id", "value": f"{gene}.1"},
            {"name": "project_id", "value": "PlasmoDB"},
        ],
        "recordClassName": "TranscriptRecordClasses.TranscriptRecordClass",
        "attributes": text,
        "tables": {},
        "tableErrors": [],
    }


def _answer() -> dict[str, object]:
    records = [
        _record(gene, _STRAIN if gene.startswith("PfDd2") else _REFERENCE)
        for target in _PAIRS
        for gene in target.genes
    ]
    count = len(records)
    return {
        "meta": {
            "totalCount": count,
            "responseCount": count,
            "displayTotalCount": count,
            "viewTotalCount": count,
            "displayViewTotalCount": count,
            "recordClassName": "transcript",
            "attributes": list(GENE_ATTRIBUTES),
            "tables": [],
        },
        "records": records,
    }


@contextmanager
def listed_genes(unanswered: int = 0) -> Iterator[respx.Route]:
    reports = [httpx.ConnectError("refused")] * unanswered
    service = get_site("plasmodb").service_url
    token = veupathdb_auth_token_ctx.set("a-registered-token")
    try:
        with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
            router.get(f"{get_site('plasmodb').web_base_url}/app").mock(
                return_value=httpx.Response(200)
            )
            router.get(f"{service}/users/current").mock(
                return_value=httpx.Response(200, json={"id": _USER, "isGuest": False})
            )
            router.post(
                f"{service}/record-types/transcript/searches/GeneByLocusTag/reports/standard"
            ).mock(side_effect=[*reports, *[httpx.Response(200, json=_answer())] * 4])
            yield router.post(f"{service}/users/{_USER}/datasets").mock(
                return_value=httpx.Response(200, json={"id": _DATASET})
            )
    finally:
        veupathdb_auth_token_ctx.reset(token)


@pytest.fixture
def screen_list_read_on_the_wire_and_record_reads_faked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    faked_site(monkeypatch)
    faked_checks(monkeypatch)
    monkeypatch.setattr(screen, "upload_gene_list", upload_gene_list)
    monkeypatch.setattr(screen, "read_gene_list", read_gene_list)


async def _carried_through(
    run_id: UUID, owner: RunOwner, stages: tuple[StageBody, ...]
) -> None:
    for stage in stages:
        await carried(
            stage, await owned_run(run_id, owner), RecordedLane(), seconds=3600
        )


async def _stored_stages(run_id: UUID, owner: RunOwner) -> RunStages:
    async with async_session_factory() as session:
        read = await AuditRepository(session).run(run_id, user_id=owner.user_id)
    assert read is not None
    return read.stages


@pytest.mark.usefixtures("screen_list_read_on_the_wire_and_record_reads_faked")
async def test_a_run_and_a_rerun_of_its_finished_screen_create_one_dataset() -> None:
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=_PAIRS)
    )

    with listed_genes() as uploads:
        await _carried_through(run_id, owner, _STAGES)
        await _carried_through(run_id, owner, (screen.run_screen_stage,))

    async with async_session_factory() as session:
        found = await AuditFindingRepository(session).findings(run_id, FindingFilter())
    assert uploads.call_count == 1
    assert {(f.genome, f.status) for f in found} == {(_STRAIN, "confirmed")}
    assert len(found) == len(_PAIRS)


@pytest.mark.usefixtures("screen_list_read_on_the_wire_and_record_reads_faked")
async def test_a_screen_resumed_after_an_unanswered_list_read_uploads_no_more() -> None:
    owner = await seed_thread()
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=_PAIRS)
    )

    with listed_genes(unanswered=6) as uploads:
        await _carried_through(run_id, owner, _STAGES[:2])

    async with async_session_factory() as session:
        found = await AuditFindingRepository(session).findings(run_id, FindingFilter())
    stages = await _stored_stages(run_id, owner)
    assert uploads.call_count == 1
    assert stages.target_list is not None
    assert (stages.target_list.dataset_id, stages.target_list.size) == (_DATASET, 300)
    assert {(f.genome, f.status) for f in found} == {(_STRAIN, "screened")}


@pytest.mark.usefixtures("screen_list_read_on_the_wire_and_record_reads_faked")
async def test_a_run_that_screens_genomes_and_names_no_target_creates_none() -> None:
    owner = await seed_thread()
    scope = AuditScope(
        site_id="plasmodb",
        genomes=(NF54,),
        comparison=relative_organisms(9),
        checks=("gene_length", "gene_split"),
    )
    run_id = await create_run(owner=owner, scope=scope)

    with listed_genes() as uploads:
        await _carried_through(run_id, owner, _STAGES[:2])
        await _carried_through(run_id, owner, (screen.run_screen_stage,))

    assert uploads.call_count == 0


async def _pseudogene_reading_the_store(
    site_id: str, strain_gene: str, reference_gene: str
) -> PseudogeneCallAudit:
    del site_id, strain_gene, reference_gene
    for _ in range(_WDK_READS):
        get_observer().on_wdk_request(0.01, _REQUEST)
    for _ in range(_STORE_READS):
        get_observer().on_jbrowse_request(0.01, _REQUEST)
    return PIGA_INTACT


async def test_a_run_counts_its_store_reads(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(checks, "audit_pseudogene_call", _pseudogene_reading_the_store)
    owner = await seed_thread()
    target = GenePairTarget(check="pseudogene_call", genes=(NF54_PIGA, PIGA))
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=(target,))
    )
    async with async_session_factory() as session:
        await AuditFindingRepository(session).add_findings(
            run_id,
            [NewFinding(genome=NF54, target=target, sampled=True, status="screened")],
        )
        await session.commit()

    with observed_requests():
        await _carried_through(run_id, owner, (confirm.run_confirm_stage,))

    stages = await _stored_stages(run_id, owner)
    async with async_session_factory() as session:
        (finding,) = await AuditFindingRepository(session).findings(
            run_id, FindingFilter()
        )
    assert [(s.name, s.requests, s.store_reads) for s in stages.stages] == [
        ("collect", 0, 0),
        ("screen", 0, 0),
        ("confirm", _WDK_READS, _STORE_READS),
        ("tie_break", 0, 0),
    ]
    assert finding.requests == _WDK_READS
    async with client_for(app, owner.user_id) as client:
        view = (await client.get(f"/api/v1/audits/{run_id}")).json()
    assert (view["requests"], view["storeReads"]) == (_WDK_READS, _STORE_READS)
