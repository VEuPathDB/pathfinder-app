from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.platform.db import async_session_factory
from fastapi import FastAPI
from langchain_core.runnables import RunnableConfig
from procrastinate.testing import InMemoryConnector
from veupathdb_mcp.audit import GeneId, PseudogeneCallAudit

from pathfinder.ai.audit.run_tools import START_TOOL
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import turn_contract
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.domain.audit.confirmations import PseudogeneConfirmation
from pathfinder.domain.audit.findings import ConfirmationEvidence
from pathfinder.domain.audit.scope import AuditScope, GenePairTarget
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    NewFinding,
    SettledFinding,
)
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.audit.runs import RunOwner, create_run
from pathfinder.tests._support.audit_planning import STRAINS
from pathfinder.tests.integration.chat._helpers import (
    chat_turn_jobs,
    parse_sse_body,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)
from pathfinder.tests.integration.http.conftest import client_for
from pathfinder.tests.integration.jobs._audit_jobs import (
    TOKEN,
)

_OK = 200
STRAIN = "EXA_0001"
REFERENCE = "EXR_0001"
GENOME = STRAINS[0]
QUESTION = (
    f"is the pseudogene call on {STRAIN} right; its reference gene is {REFERENCE}"
)


def intact() -> PseudogeneCallAudit:
    return PseudogeneCallAudit(
        verdict="INTACT",
        reference_cds_length=900,
        strain_cds_length=900,
        covered=900,
        premature_stops=[],
        residue_differences=0,
        gene_ids=[
            GeneId(given=STRAIN, resolved=STRAIN),
            GeneId(given=REFERENCE, resolved=REFERENCE),
        ],
        strain_gene=STRAIN,
        reference_gene=REFERENCE,
    )


async def post(
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


def approved(
    thread: UUID, call_id: str, approval_id: str, *, approved: bool = True
) -> dict[str, Any]:
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
                        "approval": {"id": approval_id, "approved": approved},
                    },
                ],
            },
        ],
        "conversationId": str(thread),
        "siteId": "plasmodb",
    }


def of_type(chunks: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [chunk for chunk in chunks if chunk["type"] == kind]


def called(chunks: list[dict[str, Any]]) -> list[str]:
    calls = (c["toolName"] for c in of_type(chunks, "tool-input-available"))
    return [name for name in calls if name != "final_result"]


def text(chunks: list[dict[str, Any]]) -> str:
    return "".join(c["delta"] for c in of_type(chunks, "text-delta"))


def summaries(chunks: list[dict[str, Any]]) -> list[str]:
    return [
        str(chunk["data"]["summary"])
        for chunk in chunks
        if chunk["type"].startswith("data-") and "summary" in chunk.get("data", {})
    ]


async def domain_of(thread: UUID) -> StrategyDomainState:
    spec = get_assistant_registry().resolve(PATHFINDER_ASSISTANT_ID)
    config: RunnableConfig = {"configurable": {"thread_id": str(thread)}}
    async with lifespan_checkpointer(get_settings().database_url) as saver:
        snapshot = await spec.build_graph(saver).aget_state(config)
    return StrategyDomainState.model_validate(snapshot.values["domain"])


async def stored_finding(owner: RunOwner) -> int:
    pair = GenePairTarget(check="pseudogene_call", genes=(STRAIN, REFERENCE))
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=(pair,))
    )
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [NewFinding(genome=GENOME, target=pair, sampled=True, status="screened")],
        )
        (finding,) = await repo.findings(run_id, FindingFilter())
        await repo.try_finding(finding.id)
        await repo.settle_finding(
            finding.id,
            SettledFinding(
                status="confirmed",
                error_type="intact_gene_called_pseudogene",
                certainty="high",
            ),
        )
        await repo.try_evidence(finding.id, "confirmation")
        await repo.save_evidence(
            finding.id,
            ConfirmationEvidence(confirmation=PseudogeneConfirmation(result=intact())),
            requests=2,
        )
        await session.commit()
    return finding.id


def watched_corrections(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    seen: list[int] = []
    held = turn_contract.to_correct

    def watched(*args: Any) -> list[turn_contract.Mismatch]:
        found = held(*args)
        seen.append(len(found))
        return found

    monkeypatch.setattr(turn_contract, "to_correct", watched)
    return seen
