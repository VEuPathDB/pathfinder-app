from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import replace
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.platform.db import async_session_factory
from fastapi import FastAPI
from langchain_core.runnables import RunnableConfig
from procrastinate.testing import InMemoryConnector
from pydantic_ai.usage import RunUsage
from veupathdb_mcp.audit import GeneId, PseudogeneCallAudit

from pathfinder.ai.audit.run_tools import START_TOOL
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead import lead_audit, turn_contract
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, SubAgentRunUsage
from pathfinder.ai.models.mock import get_mock_model
from pathfinder.ai.models.mock.audit_arcs import START_REPLY
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.domain.audit.confirmations import PseudogeneConfirmation
from pathfinder.domain.audit.findings import ConfirmationEvidence
from pathfinder.domain.audit.planning import START_LABEL, PlanRequest
from pathfinder.domain.audit.scope import AuditScope, GenePairTarget
from pathfinder.domain.statistic_facts import statistic_id
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    NewFinding,
    SettledFinding,
)
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.audit import investigation
from pathfinder.services.audit.planning import propose_scope
from pathfinder.services.audit.runs import RunOwner, create_run
from pathfinder.services.audit.verdicts import conversation_verdicts
from pathfinder.services.gene_records.read import gene_record_url
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests._support.audit_planning import STRAINS, faked_site
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests._support.run_context import run_context_for, turn_runtime
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
    chat_turn_jobs,
    parse_sse_body,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)
from pathfinder.tests.integration.http.conftest import client_for
from pathfinder.tests.integration.jobs._audit_jobs import (
    TOKEN,
    audit_jobs,
    registered,
)

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "signed_in_to_veupathdb"
)

_OK = 200
_STRAIN = "EXA_0001"
_REFERENCE = "EXR_0001"
_GENOME = STRAINS[0]
_AUDIT = f"[[arc:audit]] Audit the gene models of {_GENOME} against its relatives"
_FINDING = "[[arc:audit-finding]] Is finding 1 real?"
_SPELLED = "[[arc:audit-finding-spelled]] Is finding 1 real?"
_QUESTION = (
    f"is the pseudogene call on {_STRAIN} right; its reference gene is {_REFERENCE}"
)
_RENDERED = (
    f"The model of [{_STRAIN}]({gene_record_url('plasmodb', _STRAIN)}) holds a CDS "
    "of 900 bases."
)
_CALLED_FOR_A_FINDING = [
    "classify_user_intent",
    "list_audit_runs",
    "list_audit_findings",
    "read_audit_findings",
]


def _intact() -> PseudogeneCallAudit:
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
        return _intact()

    monkeypatch.setattr(investigation, "audit_pseudogene_call", answer)


@pytest.fixture
def corrections(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    seen: list[int] = []
    held = turn_contract.to_correct

    def watched(*args: Any) -> list[turn_contract.Mismatch]:
        found = held(*args)
        seen.append(len(found))
        return found

    monkeypatch.setattr(turn_contract, "to_correct", watched)
    return seen


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


def _approved(thread: UUID, call_id: str, approval_id: str) -> dict[str, Any]:
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
        "conversationId": str(thread),
        "siteId": "plasmodb",
    }


def _of_type(chunks: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [chunk for chunk in chunks if chunk["type"] == kind]


def _called(chunks: list[dict[str, Any]]) -> list[str]:
    calls = (c["toolName"] for c in _of_type(chunks, "tool-input-available"))
    return [name for name in calls if name != "final_result"]


def _text(chunks: list[dict[str, Any]]) -> str:
    return "".join(c["delta"] for c in _of_type(chunks, "text-delta"))


def _summaries(chunks: list[dict[str, Any]]) -> list[str]:
    return [
        str(chunk["data"]["summary"])
        for chunk in chunks
        if chunk["type"].startswith("data-") and "summary" in chunk.get("data", {})
    ]


async def _domain(thread: UUID) -> StrategyDomainState:
    spec = get_assistant_registry().resolve(PATHFINDER_ASSISTANT_ID)
    config: RunnableConfig = {"configurable": {"thread_id": str(thread)}}
    async with lifespan_checkpointer(get_settings().database_url) as saver:
        snapshot = await spec.build_graph(saver).aget_state(config)
    return StrategyDomainState.model_validate(snapshot.values["domain"])


async def _stored_finding(owner: RunOwner) -> int:
    pair = GenePairTarget(check="pseudogene_call", genes=(_STRAIN, _REFERENCE))
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=(pair,))
    )
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [NewFinding(genome=_GENOME, target=pair, sampled=True, status="screened")],
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
            ConfirmationEvidence(confirmation=PseudogeneConfirmation(result=_intact())),
            requests=2,
        )
        await session.commit()
    return finding.id


@pytest.mark.usefixtures("signed_in")
async def test_the_lead_asks_before_an_audit_starts(
    in_memory_jobs: InMemoryConnector,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    faked_site(monkeypatch)
    owner = await seed_thread()
    thread = owner.conversation_id

    asked = await _post(
        app, owner.user_id, in_memory_jobs, chat_post_body(thread, _AUDIT)
    )

    (approval,) = _of_type(asked, "tool-approval-request")
    (card,) = _of_type(asked, "data-audit-start")
    assert _called(asked) == [
        "classify_user_intent",
        "plan_gene_model_audit",
        START_TOOL,
    ]
    assert "Intent: gene_model_audit" in _summaries(asked)
    assert START_LABEL in _summaries(asked)
    assert card["id"] == approval["toolCallId"]
    assert card["data"]["genomes"] == [_GENOME]
    assert _text(asked) == START_REPLY
    async with async_session_factory() as session:
        assert await AuditRepository(session).runs(user_id=owner.user_id) == []
    assert audit_jobs(in_memory_jobs) == []

    started = await _post(
        app,
        owner.user_id,
        in_memory_jobs,
        _approved(thread, approval["toolCallId"], approval["approvalId"]),
    )

    async with async_session_factory() as session:
        (run,) = await AuditRepository(session).runs(user_id=owner.user_id)
    assert run.conversation_id == thread
    assert len(audit_jobs(in_memory_jobs)) == 1
    assert _text(started).endswith(f"Audit run {run.id} is planned.")


async def test_an_audit_request_is_not_the_threads_strategy_request(
    in_memory_jobs: InMemoryConnector,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    faked_site(monkeypatch)
    owner = await seed_thread()

    await _post(
        app,
        owner.user_id,
        in_memory_jobs,
        chat_post_body(owner.conversation_id, _AUDIT),
    )

    domain = await _domain(owner.conversation_id)
    assert domain.user_intent is not None
    assert domain.user_intent.classification.value == "gene_model_audit"
    assert domain.original_request == ""
    assert domain.operational_spec is None


async def test_the_lead_answers_with_the_plans_request_count(
    in_memory_jobs: InMemoryConnector,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    corrections: list[int],
) -> None:
    faked_site(monkeypatch)
    owner = await seed_thread()
    proposal = await propose_scope(PlanRequest(site_id="plasmodb", genomes=STRAINS))
    assert proposal.estimate is not None
    assert proposal.left_out
    prompt = f"[[arc:audit-plan]] Audit the gene models of {', '.join(STRAINS)}"

    chunks = await _post(
        app,
        owner.user_id,
        in_memory_jobs,
        chat_post_body(owner.conversation_id, prompt),
    )

    assert _called(chunks) == ["classify_user_intent", "plan_gene_model_audit"]
    assert _text(chunks) == (
        f"The run reads the site {proposal.estimate.wdk_requests} times, and the "
        f"plan leaves out {proposal.left_out[0]}."
    )
    assert corrections == [0]


async def test_the_lead_answers_a_finding_question_from_the_stored_evidence(
    in_memory_jobs: InMemoryConnector,
    app: FastAPI,
    corrections: list[int],
) -> None:
    owner = await seed_thread()
    await _stored_finding(owner)

    chunks = await _post(
        app,
        owner.user_id,
        in_memory_jobs,
        chat_post_body(owner.conversation_id, _FINDING),
    )

    assert _called(chunks) == _CALLED_FOR_A_FINDING
    assert _text(chunks) == _RENDERED
    assert corrections == [0]


async def test_a_literal_number_in_a_finding_answer_is_corrected(
    in_memory_jobs: InMemoryConnector,
    app: FastAPI,
    corrections: list[int],
) -> None:
    owner = await seed_thread()
    await _stored_finding(owner)

    chunks = await _post(
        app,
        owner.user_id,
        in_memory_jobs,
        chat_post_body(owner.conversation_id, _SPELLED),
    )

    assert _called(chunks) == _CALLED_FOR_A_FINDING
    assert corrections == [1, 0]
    assert _text(chunks) == _RENDERED


def _lead_context(owner: RunOwner, recorded: list[SubAgentRunUsage]) -> LeadDeps:
    state = PipelineState(
        conversation_id=owner.conversation_id,
        user_id=owner.user_id,
        site_id="plasmodb",
        mode="strategy",
        user_prompt=_QUESTION,
    )
    return LeadDeps(
        state=state,
        intent=None,
        runtime=turn_runtime(user_id=owner.user_id),
        retrieved_memories=[],
        record_sub_agent_usage=recorded.append,
    )


@pytest.mark.usefixtures("pseudogene_call")
async def test_the_lead_sends_a_gene_model_question_to_the_investigator() -> None:
    owner = await seed_thread()
    recorded: list[SubAgentRunUsage] = []
    deps = _lead_context(owner, recorded)
    lead_usage = RunUsage(requests=30, tool_calls=30, input_tokens=9000)
    ctx = replace(
        run_context_for(deps, "call_investigate"),
        model=get_mock_model(),
        usage=lead_usage,
    )

    await lead_audit.investigate_gene_models(ctx, _QUESTION)

    assert ctx.usage == RunUsage(requests=30, tool_calls=30, input_tokens=9000)
    (spent,) = recorded
    assert (spent.parent_tool_call_id, spent.billed) == ("call_investigate", True)
    assert (spent.usage.requests, spent.usage.tool_calls) == (2, 1)
    (stored,) = await conversation_verdicts(owner.conversation_id, owner.user_id)
    assert (stored.origin, stored.verdict.error_type) == (
        "lead",
        "intact_gene_called_pseudogene",
    )
    markers = deps.state.turn_markers
    assert [fact.id for fact in markers.audit_facts] == [
        statistic_id("gene_check", ["audit_pseudogene_call", _STRAIN, _REFERENCE])
    ]
    assert [gene.record_id for gene in markers.resolved_genes] == [
        _STRAIN,
        _REFERENCE,
    ]


@pytest.mark.usefixtures("pseudogene_call")
async def test_the_lead_answers_a_gene_model_question_with_the_investigation(
    in_memory_jobs: InMemoryConnector,
    app: FastAPI,
    corrections: list[int],
) -> None:
    owner = await seed_thread()
    prompt = f"[[arc:audit-investigation]] {_QUESTION}"

    chunks = await _post(
        app,
        owner.user_id,
        in_memory_jobs,
        chat_post_body(owner.conversation_id, prompt),
    )

    assert _called(chunks) == ["classify_user_intent", "investigate_gene_models"]
    assert _text(chunks) == (
        f"The check reads the model of [{_STRAIN}]"
        f"({gene_record_url('plasmodb', _STRAIN)}) as INTACT."
    )
    assert corrections == [0]
    (stored,) = await conversation_verdicts(owner.conversation_id, owner.user_id)
    assert stored.origin == "lead"
