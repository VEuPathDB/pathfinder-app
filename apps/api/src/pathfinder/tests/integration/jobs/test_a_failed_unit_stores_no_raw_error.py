from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pydantic
import pytest
from assistant_core.platform.db import async_session_factory
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from veupathdb_mcp.tools import audit_pseudogene_call

from pathfinder.domain.audit.stages import StageName
from pathfinder.persistence.models import AuditFindingRecord
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import AuditFindingRepository
from pathfinder.platform.config import get_settings
from pathfinder.services.audit import checks, collect, weighing
from pathfinder.services.audit.job import start_run
from pathfinder.services.audit.runs import RunOwner, create_run, owned_run
from pathfinder.tests._support.audit import NF54_PIGA, seed_thread
from pathfinder.tests._support.audit_wire import gene_records_answering
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests._support.rendered_logs import rendered_logs
from pathfinder.tests.integration.http.conftest import client_for
from pathfinder.tests.integration.jobs._audit_jobs import (
    SCOPE,
    TOKEN,
    holding,
    queued,
    registered,
    wire_checks,
    work,
    work_through,
)

_SECRET = "api_key=held-in-the-query"
_URL = f"https://qa.plasmodb.org/plasmo.qa/service/answer?{_SECRET}"
_GENERIC = "An internal error occurred"
_LOG_EVENT = "An audit unit failed"
_REFERENCE_GENOME = SCOPE.comparison[0]


def _status_error() -> httpx.HTTPStatusError:
    request = httpx.Request("GET", _URL)
    response = httpx.Response(404, request=request)
    return httpx.HTTPStatusError(f"404 for {_URL}", request=request, response=response)


def _validation_error() -> pydantic.ValidationError:
    try:
        pydantic.TypeAdapter(int).validate_python(_SECRET)
    except pydantic.ValidationError as exc:
        return exc
    raise AssertionError


_ERRORS = [_status_error(), _validation_error()]


@pytest.fixture
def jobs(
    db_cleaner: None,
    patch_app_db_engine: None,
    site_login_names_the_user: None,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[InMemoryConnector]:
    del db_cleaner, patch_app_db_engine, site_login_names_the_user
    registered(monkeypatch, TOKEN)
    with sealed_provider_keys(monkeypatch), holding(TOKEN):
        yield in_memory_jobs
    get_settings.cache_clear()


async def _finished_run(jobs: InMemoryConnector) -> tuple[RunOwner, UUID]:
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)
    await work_through(jobs)
    return owner, run_id


@pytest.mark.parametrize("error", _ERRORS)
async def test_a_failed_genome_reads_as_its_type_in_the_row_and_the_route(
    jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
    app: FastAPI,
    error: Exception,
) -> None:
    fakes = wire_checks(monkeypatch)

    async def genes(site_id: str, organism: str) -> object:
        if organism == _REFERENCE_GENOME:
            raise error
        return await fakes.site.genes_of_genome(site_id, organism)

    monkeypatch.setattr(collect, "genes_of_genome", genes)
    owner, run_id = await _finished_run(jobs)
    stated = f"{type(error).__name__}: {_GENERIC}"
    async with async_session_factory() as session:
        states = await AuditRepository(session).genome_states(run_id)
    assert {s.message for s in states if s.organism == _REFERENCE_GENOME} == {stated}
    async with client_for(app, owner.user_id) as client:
        response = await client.get(f"/api/v1/audits/{run_id}")
    shown = [
        genome["message"]
        for genome in response.json()["genomes"]
        if genome["organism"] == _REFERENCE_GENOME
    ]
    assert shown == [stated]
    assert _SECRET not in response.text


@pytest.mark.parametrize("error", _ERRORS)
async def test_a_failed_finding_reads_as_its_type_in_the_row_and_the_route(
    jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
    app: FastAPI,
    error: Exception,
) -> None:
    fakes = wire_checks(monkeypatch)
    fakes.split_failures = [error]
    owner, run_id = await _finished_run(jobs)
    stated = f"{type(error).__name__}: {_GENERIC}"
    async with async_session_factory() as session:
        (split,) = await AuditFindingRepository(session).findings(
            run_id, FindingFilter(checks=("gene_split",))
        )
    assert (split.status, split.message) == ("failed", stated)
    async with client_for(app, owner.user_id) as client:
        listed = await client.get(f"/api/v1/audits/{run_id}/findings")
        detail = await client.get(f"/api/v1/audits/{run_id}/findings/{split.id}")
    assert detail.json()["finding"]["message"] == stated
    assert _SECRET not in listed.text
    assert _SECRET not in detail.text


@pytest.mark.parametrize("error", _ERRORS)
async def test_failed_evidence_reads_as_its_type_in_the_row_and_the_route(
    jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
    app: FastAPI,
    error: Exception,
) -> None:
    wire_checks(monkeypatch)

    async def evidence(site_id: str, gene: str) -> object:
        del site_id, gene
        raise error

    monkeypatch.setattr(weighing, "audit_gene_evidence", evidence)
    owner, run_id = await _finished_run(jobs)
    stated = f"{type(error).__name__}: {_GENERIC}"
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        found = await repo.findings(run_id, FindingFilter(checks=("pseudogene_call",)))
        (piga,) = [f for f in found if NF54_PIGA in f.target.genes]
        stored = await repo.evidence(run_id, [piga.id], kinds=("gene_evidence",))
    assert [(row.status, row.message) for row in stored] == [("failed", stated)]
    async with client_for(app, owner.user_id) as client:
        detail = await client.get(f"/api/v1/audits/{run_id}/findings/{piga.id}")
    shown = [
        row["message"]
        for row in detail.json()["evidence"]
        if row["kind"] == "gene_evidence"
    ]
    assert shown == [stated]
    assert _SECRET not in detail.text


async def test_a_release_read_that_fails_notes_only_its_type(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch, app: FastAPI
) -> None:
    wire_checks(monkeypatch)

    async def build(site_id: str) -> str:
        del site_id
        raise _status_error()

    monkeypatch.setattr(collect, "site_build", build)
    owner, run_id = await _finished_run(jobs)
    async with client_for(app, owner.user_id) as client:
        response = await client.get(f"/api/v1/audits/{run_id}")
    assert response.json()["stages"]["stages"][0]["message"] == (
        f"release unknown: HTTPStatusError: {_GENERIC}"
    )
    assert (await owned_run(run_id, owner)).release is None
    assert _SECRET not in response.text


async def test_the_full_error_of_a_unit_stays_in_the_log_with_the_run_bound(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    fakes = wire_checks(monkeypatch)
    fakes.split_failures = [_status_error()]
    with rendered_logs() as logs:
        _, run_id = await _finished_run(jobs)
    (line,) = [entry for entry in logs.lines() if entry["event"] == _LOG_EVENT]
    assert line["run_id"] == str(run_id)
    assert _SECRET in str(line["exception"])


_BODY = "java.lang.NullPointerException at org.gusdb.wdk.Secret"


def _spied_stage_lines(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    lines: list[str] = []
    kept = AuditRepository.record_progress

    async def spied(
        self: AuditRepository,
        run_id: UUID,
        stage: StageName,
        *,
        done: int,
        total: int,
        message: str,
    ) -> None:
        lines.append(message)
        await kept(self, run_id, stage, done=done, total=total, message=message)

    monkeypatch.setattr(AuditRepository, "record_progress", spied)
    return lines


async def _target(run_id: UUID) -> AuditFindingRecord:
    async with async_session_factory() as session:
        (found,) = await AuditFindingRepository(session).findings(
            run_id, FindingFilter(checks=("pseudogene_call",))
        )
    return found


async def _shown(
    app: FastAPI, owner: RunOwner, run_id: UUID, finding_id: int
) -> list[httpx.Response]:
    async with client_for(app, owner.user_id) as client:
        return [
            await client.get(f"/api/v1/audits/{run_id}"),
            await client.get(f"/api/v1/audits/{run_id}/findings"),
            await client.get(f"/api/v1/audits/{run_id}/findings/{finding_id}"),
        ]


async def test_a_read_the_site_refused_shows_a_fixed_sentence_everywhere(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch, app: FastAPI
) -> None:
    wire_checks(monkeypatch)
    monkeypatch.setattr(checks, "audit_pseudogene_call", audit_pseudogene_call)
    lines = _spied_stage_lines(monkeypatch)
    with gene_records_answering(httpx.Response(422, text=f"<html>{_BODY}</html>")):
        owner, run_id = await _finished_run(jobs)
    stated = "plasmodb answered 422 to the audit reads"
    found = await _target(run_id)
    assert (found.status, found.message) == ("failed", stated)
    responses = await _shown(app, owner, run_id, found.id)
    assert [r.status_code for r in responses] == [200, 200, 200]
    assert responses[2].json()["finding"]["message"] == stated
    for response in responses:
        assert [
            t for t in (_BODY, "record-types", "HTTP 422") if t in response.text
        ] == []
    assert [t for t in lines if _BODY in t or "HTTP 422" in t] == []
    assert [t for t in lines if stated in t] != []


async def test_a_read_the_site_never_answered_shows_a_fixed_sentence_everywhere(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch, app: FastAPI
) -> None:
    wire_checks(monkeypatch)
    monkeypatch.setattr(checks, "audit_pseudogene_call", audit_pseudogene_call)
    lines = _spied_stage_lines(monkeypatch)
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)
    with gene_records_answering(httpx.ConnectError(f"no route to {_URL}")):
        await work(jobs, queued(jobs)[0])
        (later,) = queued(jobs)
        later["args"]["payload"]["deadline"] = datetime.now(UTC).isoformat()
        await work_through(jobs)
    stated = "plasmodb did not answer the audit reads"
    found = await _target(run_id)
    assert (found.status, found.message) == ("unreached", stated)
    responses = await _shown(app, owner, run_id, found.id)
    for response in responses:
        assert [t for t in (_SECRET, "service/answer") if t in response.text] == []
    assert [t for t in lines if _SECRET in t] == []
