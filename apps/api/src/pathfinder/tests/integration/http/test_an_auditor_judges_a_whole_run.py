from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.platform.db import async_session_factory
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.audit import mock_run
from pathfinder.ai.audit.budget_stop import budget_stop_prose
from pathfinder.ai.audit.mock import AUDITOR_GREETING
from pathfinder.domain.audit.scope import AuditScope, SingleGeneTarget
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
    NewFinding,
    SettledFinding,
)
from pathfinder.platform.identity import AUDIT_ASSISTANT_ID
from pathfinder.services.audit.runs import RunOwner, create_run
from pathfinder.services.audit.verdicts import conversation_verdicts
from pathfinder.tests._support.audit_planning import STRAINS
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
    chat_turn_jobs,
    parse_sse_body,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)
from pathfinder.tests.integration.http.conftest import client_for, make_user
from pathfinder.tests.integration.jobs._audit_jobs import TOKEN

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "signed_in_to_veupathdb"
)

_GENOME = STRAINS[0]
_FINDINGS = 29
_READ = "read_audit_findings"
_RECORD = "record_gene_model_verdicts"


async def _post(
    app: FastAPI, user_id: UUID, connector: InMemoryConnector, body: dict[str, Any]
) -> list[dict[str, Any]]:
    queued = len(chat_turn_jobs(connector))
    async with client_for(app, user_id, wdk_token=TOKEN) as client:
        task = asyncio.create_task(client.post("/api/v1/chat", json=body, timeout=60.0))
        await asyncio.wait_for(wait_until_chat_turn_deferred(connector, queued), 10.0)
        await run_deferred_chat_turns()
        response = await asyncio.wait_for(task, 60.0)
    assert response.status_code == 200, response.text
    return parse_sse_body(response.text)


def _asked(conversation_id: UUID, prompt: str) -> dict[str, Any]:
    body = chat_post_body(conversation_id, prompt)
    body["assistantId"] = AUDIT_ASSISTANT_ID
    return body


def _of_type(chunks: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [chunk for chunk in chunks if chunk["type"] == kind]


def _called(chunks: list[dict[str, Any]]) -> list[str]:
    return [c["toolName"] for c in _of_type(chunks, "tool-input-available")]


def _text(chunks: list[dict[str, Any]]) -> str:
    return "".join(c["delta"] for c in _of_type(chunks, "text-delta"))


async def _run_of(owner: RunOwner) -> UUID:
    scope = AuditScope(site_id="plasmodb", genomes=(_GENOME,), checks=("gene_length",))
    run_id = await create_run(owner=owner, scope=scope)
    targets = [
        SingleGeneTarget(check="gene_length", genes=(f"EXA_{k:04d}",))
        for k in range(_FINDINGS)
    ]
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
            named = k % 3 == 0
            await repo.try_finding(finding.id)
            await repo.settle_finding(
                finding.id,
                SettledFinding(
                    status="confirmed",
                    error_type="truncated_model" if named else None,
                    certainty="high" if named else None,
                ),
            )
        await session.commit()
    return run_id


async def _judged(
    app: FastAPI, db_session: AsyncSession, connector: InMemoryConnector
) -> tuple[list[dict[str, Any]], UUID, UUID]:
    owner = await make_user(db_session)
    thread = uuid4()
    await _post(app, owner.id, connector, _asked(thread, "hello"))
    run_id = await _run_of(RunOwner(user_id=owner.id, conversation_id=thread))
    prompt = f"Judge every finding of audit run {run_id}"
    chunks = await _post(app, owner.id, connector, _asked(thread, prompt))
    return chunks, thread, owner.id


async def test_the_auditor_judges_every_finding_of_a_large_run(
    app: FastAPI, db_session: AsyncSession, in_memory_jobs: InMemoryConnector
) -> None:
    chunks, thread, owner = await _judged(app, db_session, in_memory_jobs)

    stored = await conversation_verdicts(thread, owner)
    assert _called(chunks) == ["list_audit_findings", _READ, _RECORD, _READ, _RECORD]
    assert len(stored) == _FINDINGS
    assert sorted(v.verdict.verdict for v in stored).count("error") == 10
    assert _of_type(chunks, "error") == []
    assert _text(chunks) == mock_run.JUDGED_EVERY_FINDING


async def test_an_auditor_turn_at_its_limit_keeps_its_verdicts(
    app: FastAPI,
    db_session: AsyncSession,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mock_run, "FINDINGS_PER_MOCK_CALL", 1)

    chunks, thread, owner = await _judged(app, db_session, in_memory_jobs)
    after = await _post(app, owner, in_memory_jobs, _asked(thread, "hello"))

    stored = await conversation_verdicts(thread, owner)
    assert len(_called(chunks)) == 40
    assert len(stored) == 19
    assert _of_type(chunks, "error") == []
    assert _text(chunks) == budget_stop_prose(19)
    assert _text(chunks) == (
        "I stopped this turn at its limit of model requests and tool calls, before "
        "I finished. I stored 19 verdicts in this turn, and each one is kept. Ask "
        "me to go on and I judge the findings that have no verdict yet."
    )
    assert _text(after) == AUDITOR_GREETING
