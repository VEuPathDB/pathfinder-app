from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb_mcp.audit import GeneId, PseudogeneCallAudit

from pathfinder.ai.audit import reply
from pathfinder.ai.audit.budget_stop import budget_stop_prose
from pathfinder.ai.audit.check_tools import CHECK_TOOL_NAMES
from pathfinder.ai.audit.mock import AUDITOR_GREETING
from pathfinder.ai.audit.run_tools import START_TOOL
from pathfinder.domain.audit.planning import START_LABEL
from pathfinder.domain.audit.scope import AuditScope, SingleGeneTarget
from pathfinder.domain.reply_note import note_facts
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    NewFinding,
    SettledFinding,
)
from pathfinder.platform.identity import AUDIT_ASSISTANT_ID, PATHFINDER_ASSISTANT_ID
from pathfinder.services.audit import investigation
from pathfinder.services.audit.runs import RunOwner, create_run
from pathfinder.services.audit.verdicts import conversation_verdicts
from pathfinder.services.audit.views import run_view
from pathfinder.services.gene_records.read import gene_record_url
from pathfinder.tests._support.audit_planning import (
    STRAINS,
    serve_gene_genomes,
)
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
    chat_turn_jobs,
    parse_sse_body,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)
from pathfinder.tests.integration.http.conftest import client_for, make_user
from pathfinder.tests.integration.jobs._audit_jobs import (
    TOKEN,
    audit_jobs,
    registered,
)

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "signed_in_to_veupathdb", "audit_site"
)

_OK = 200
_CONFLICT = 409
_STRAIN = "EXA_0001"
_REFERENCE = "EXR_0001"
_GENOME = STRAINS[0]
_PSEUDOGENE_QUESTION = (
    f"is the pseudogene call on {_STRAIN} right; its reference gene is {_REFERENCE}"
)
_RENDERED = (
    f"The check above reads the model of [{_STRAIN}]"
    f"({gene_record_url('plasmodb', _STRAIN)}) as recorded."
)


@pytest.fixture
def signed_in(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    registered(monkeypatch, TOKEN)
    with sealed_provider_keys(monkeypatch):
        yield


@pytest.fixture
def pseudogene_call(monkeypatch: pytest.MonkeyPatch) -> None:
    async def answer(
        site_id: str, strain_gene: str, reference_gene: str
    ) -> PseudogeneCallAudit:
        del site_id, strain_gene, reference_gene
        return PseudogeneCallAudit(
            verdict="INTACT",
            reference_cds_length=900,
            strain_cds_length=900,
            covered=900,
            premature_stops=[],
            residue_differences=0,
            gene_ids=[
                GeneId(given=_STRAIN, resolved=_STRAIN),
                GeneId(given=_REFERENCE, resolved=_REFERENCE),
            ],
            strain_gene=_STRAIN,
            reference_gene=_REFERENCE,
        )

    monkeypatch.setattr(investigation, "audit_pseudogene_call", answer)
    serve_gene_genomes(monkeypatch)


async def _post(
    app: FastAPI, user_id: UUID, connector: InMemoryConnector, body: dict[str, Any]
) -> list[dict[str, Any]]:
    queued = len(chat_turn_jobs(connector))
    async with client_for(app, user_id, wdk_token=TOKEN) as client:
        task = asyncio.create_task(client.post("/api/v1/chat", json=body, timeout=60.0))
        await asyncio.wait_for(wait_until_chat_turn_deferred(connector, queued), 10.0)
        await run_deferred_chat_turns()
        response = await asyncio.wait_for(task, 60.0)
    assert response.status_code == _OK, response.text
    return parse_sse_body(response.text)


def _asked(conversation_id: UUID, prompt: str) -> dict[str, Any]:
    body = chat_post_body(conversation_id, prompt)
    body["assistantId"] = AUDIT_ASSISTANT_ID
    return body


def _approved(conversation_id: UUID, call_id: str, approval_id: str) -> dict[str, Any]:
    message_id = str(uuid4())
    return {
        "trigger": "submit-message",
        "id": message_id,
        "messages": [
            {
                "id": message_id,
                "role": "assistant",
                "parts": [
                    {
                        "type": f"tool-{START_TOOL}",
                        "toolCallId": call_id,
                        "state": "approval-responded",
                        "input": {},
                        "approval": {"id": approval_id, "approved": True},
                    },
                ],
            },
        ],
        "conversationId": str(conversation_id),
        "siteId": "plasmodb",
        "assistantId": AUDIT_ASSISTANT_ID,
    }


def _of_type(chunks: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [chunk for chunk in chunks if chunk["type"] == kind]


def _called(chunks: list[dict[str, Any]]) -> list[str]:
    return [c["toolName"] for c in _of_type(chunks, "tool-input-available")]


def _text(chunks: list[dict[str, Any]]) -> str:
    return "".join(c["delta"] for c in _of_type(chunks, "text-delta"))


def _shown(chunks: list[dict[str, Any]]) -> tuple[list[str], str]:
    *facts, note = _text(chunks).split("\n\n")
    return [line for fact in facts for line in fact.splitlines()], note


def _summaries(chunks: list[dict[str, Any]]) -> list[str]:
    return [
        str(chunk["data"]["summary"])
        for chunk in chunks
        if chunk["type"].startswith("data-") and "summary" in chunk.get("data", {})
    ]


async def _assistant_of(conversation_id: UUID) -> str:
    async with async_session_factory() as session:
        found = await session.scalars(
            select(Conversation.assistant_id).where(Conversation.id == conversation_id)
        )
        return found.one()


async def test_a_thread_opens_under_the_audit_assistant(
    app: FastAPI, db_session: AsyncSession, in_memory_jobs: InMemoryConnector
) -> None:
    owner = await make_user(db_session)
    thread = uuid4()

    chunks = await _post(app, owner.id, in_memory_jobs, _asked(thread, "hello"))

    assert _text(chunks) == AUDITOR_GREETING
    assert await _assistant_of(thread) == AUDIT_ASSISTANT_ID
    other = chat_post_body(thread, "hello")
    other["assistantId"] = PATHFINDER_ASSISTANT_ID
    async with client_for(app, owner.id, wdk_token=TOKEN) as client:
        refused = await client.post("/api/v1/chat", json=other, timeout=60.0)
    assert refused.status_code == _CONFLICT


async def _parked(
    app: FastAPI, user_id: UUID, connector: InMemoryConnector, thread: UUID
) -> list[dict[str, Any]]:
    prompt = f"Audit the gene models of {_GENOME}"
    return await _post(app, user_id, connector, _asked(thread, prompt))


async def test_the_auditor_plans_and_asks_before_starting(
    app: FastAPI,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
) -> None:
    owner = await make_user(db_session)

    chunks = await _parked(app, owner.id, in_memory_jobs, uuid4())

    (asked,) = _of_type(chunks, "tool-approval-request")
    (card,) = _of_type(chunks, "data-audit-start")
    assert _called(chunks) == ["plan_gene_model_audit", START_TOOL]
    assert card["id"] == asked["toolCallId"]
    assert START_LABEL in _summaries(chunks)
    async with async_session_factory() as session:
        assert await AuditRepository(session).runs(user_id=owner.id) == []
    assert audit_jobs(in_memory_jobs) == []


@pytest.mark.usefixtures("signed_in")
async def test_an_approved_audit_starts_and_reads_its_progress(
    app: FastAPI,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
) -> None:
    owner = await make_user(db_session)
    thread = uuid4()
    (asked,) = _of_type(
        await _parked(app, owner.id, in_memory_jobs, thread), "tool-approval-request"
    )

    started = await _post(
        app,
        owner.id,
        in_memory_jobs,
        _approved(thread, asked["toolCallId"], asked["approvalId"]),
    )
    progress = await _post(
        app, owner.id, in_memory_jobs, _asked(thread, "How is the audit doing?")
    )

    async with async_session_factory() as session:
        (run,) = await AuditRepository(session).runs(user_id=owner.id)
    assert len(audit_jobs(in_memory_jobs)) == 1
    started_facts, started_note = _shown(started)
    progress_facts, progress_note = _shown(progress)
    assert (started_facts[0], "- phase: queued" in started_facts, started_note) == (
        f"**Audit run {run.id} started**",
        True,
        "The audit is started; its run and its phase are shown above.",
    )
    assert _called(progress) == ["list_audit_runs", "read_audit_run"]
    assert (
        f"**Audit run {run.id}**" in progress_facts,
        "- run phase: queued" in progress_facts,
    ) == (True, True)
    assert progress_note.startswith("The run above shows its phase")


@pytest.mark.usefixtures("pseudogene_call")
async def test_the_auditor_investigates_one_gene(
    app: FastAPI, db_session: AsyncSession, in_memory_jobs: InMemoryConnector
) -> None:
    owner = await make_user(db_session)
    thread = uuid4()

    chunks = await _post(
        app, owner.id, in_memory_jobs, _asked(thread, _PSEUDOGENE_QUESTION)
    )

    (stored,) = await conversation_verdicts(thread, owner.id)
    assert _called(chunks) == ["audit_pseudogene_call", "record_gene_model_verdicts"]
    assert (stored.origin, stored.verdict.verdict, stored.verdict.error_type) == (
        "auditor",
        "error",
        "intact_gene_called_pseudogene",
    )
    assert stored.verdict.cites == (f"audit_pseudogene_call:{_STRAIN}:{_REFERENCE}",)


def _numbers_seen(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    seen: list[list[str]] = []

    def watched(*args: Any) -> list[str]:
        written = note_facts(*args)
        seen.append(written)
        return written

    monkeypatch.setattr(reply, "note_facts", watched)
    return seen


@pytest.mark.usefixtures("pseudogene_call")
async def test_an_auditor_reply_shows_the_check_before_its_note(
    app: FastAPI,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _numbers_seen(monkeypatch)
    owner = await make_user(db_session)

    chunks = await _post(
        app, owner.id, in_memory_jobs, _asked(uuid4(), _PSEUDOGENE_QUESTION)
    )

    facts, note = _shown(chunks)
    assert ("- strain cds length: 900" in facts, note, seen) == (True, _RENDERED, [[]])


@pytest.mark.usefixtures("pseudogene_call")
async def test_an_auditor_reply_that_writes_a_number_is_corrected(
    app: FastAPI,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = _numbers_seen(monkeypatch)
    owner = await make_user(db_session)
    prompt = f"{_PSEUDOGENE_QUESTION}; spell out the length"

    chunks = await _post(app, owner.id, in_memory_jobs, _asked(uuid4(), prompt))

    assert (seen, _shown(chunks)[1]) == ([["900"], []], _RENDERED)


async def _stored_run(owner: RunOwner) -> UUID:
    scope = AuditScope(site_id="plasmodb", genomes=(_GENOME,), checks=("gene_length",))
    targets = [
        SingleGeneTarget(check="gene_length", genes=(f"EXA_00{k:02d}",))
        for k in range(10)
    ]
    run_id = await create_run(owner=owner, scope=scope)
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [
                NewFinding(genome=_GENOME, target=t, sampled=True, status="screened")
                for t in targets
            ],
        )
        for k, finding in enumerate(await repo.findings(run_id, FindingFilter())):
            named = k < 3
            await repo.try_finding(finding.id)
            await repo.settle_finding(
                finding.id,
                SettledFinding(
                    status="confirmed",
                    error_type="truncated_model" if named else None,
                    certainty="high" if named else None,
                ),
            )
        await AuditRepository(session).record_progress(
            run_id, "confirm", done=7, total=10, message="confirming"
        )
        await session.commit()
    return run_id


async def test_the_auditor_answers_progress_from_the_run_fact(
    app: FastAPI,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await make_user(db_session)
    thread = uuid4()
    await _post(app, owner.id, in_memory_jobs, _asked(thread, "hello"))
    run_id = await _stored_run(RunOwner(user_id=owner.id, conversation_id=thread))
    view = await run_view(run_id, owner.id)
    (rate,) = view.rates
    assert rate.bounds is not None
    seen = _numbers_seen(monkeypatch)

    chunks = await _post(
        app, owner.id, in_memory_jobs, _asked(thread, "How far is the audit?")
    )

    assert _called(chunks) == ["list_audit_runs", "read_audit_run"]
    facts, note = _shown(chunks)
    assert (
        seen,
        f"**Audit run {run_id}**" in facts,
        "- run phase: not started" in facts,
        note,
    ) == (
        [[]],
        True,
        True,
        (
            "The run above shows its phase and how far each stage has come. Its "
            "first genome already has an error rate."
        ),
    )


async def test_an_auditor_turn_stops_at_its_usage_limit(
    app: FastAPI, db_session: AsyncSession, in_memory_jobs: InMemoryConnector
) -> None:
    owner = await make_user(db_session)

    chunks = await _post(
        app, owner.id, in_memory_jobs, _asked(uuid4(), "check every gene")
    )

    called = _called(chunks)
    assert set(called) <= CHECK_TOOL_NAMES
    assert len(called) == 40
    assert [c["type"] for c in chunks][-2:] == ["finish", "done"]
    assert _of_type(chunks, "error") == []
    assert _shown(chunks)[1] == budget_stop_prose(0)
