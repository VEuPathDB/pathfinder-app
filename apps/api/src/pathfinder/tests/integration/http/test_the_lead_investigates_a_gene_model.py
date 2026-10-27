from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from pydantic_ai.usage import RunUsage
from veupathdb_mcp.audit import PseudogeneCallAudit

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead import lead_audit
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, SubAgentRunUsage
from pathfinder.ai.models.mock import get_mock_model
from pathfinder.domain.statistic_facts import statistic_id
from pathfinder.services.audit import investigation
from pathfinder.services.audit.runs import RunOwner
from pathfinder.services.audit.verdicts import conversation_verdicts
from pathfinder.services.gene_records.read import gene_record_url
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests._support.audit_planning import serve_gene_genomes
from pathfinder.tests._support.run_context import run_context_for, turn_runtime
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
)
from pathfinder.tests.integration.http._lead_audit_turns import (
    QUESTION,
    REFERENCE,
    STRAIN,
    called,
    intact,
    post,
    text,
    watched_corrections,
)

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "signed_in_to_veupathdb", "audit_site"
)


@pytest.fixture
def pseudogene_call(monkeypatch: pytest.MonkeyPatch) -> None:
    async def answer(
        site_id: str, strain_gene: str, reference_gene: str
    ) -> PseudogeneCallAudit:
        del site_id, strain_gene, reference_gene
        return intact()

    monkeypatch.setattr(investigation, "audit_pseudogene_call", answer)
    serve_gene_genomes(monkeypatch)


@pytest.fixture
def corrections(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    return watched_corrections(monkeypatch)


def _lead_context(owner: RunOwner, recorded: list[SubAgentRunUsage]) -> LeadDeps:
    state = PipelineState(
        conversation_id=owner.conversation_id,
        user_id=owner.user_id,
        site_id="plasmodb",
        mode="strategy",
        user_prompt=QUESTION,
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

    await lead_audit.investigate_gene_models(ctx, QUESTION)

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
        statistic_id("gene_check", ["audit_pseudogene_call", STRAIN, REFERENCE])
    ]
    assert [gene.record_id for gene in markers.records_retrieved] == [
        STRAIN,
        REFERENCE,
    ]
    assert markers.resolved_genes == []


@pytest.mark.usefixtures("pseudogene_call")
async def test_the_lead_answers_a_gene_model_question_with_the_investigation(
    in_memory_jobs: InMemoryConnector,
    app: FastAPI,
    corrections: list[int],
) -> None:
    owner = await seed_thread()
    prompt = f"[[arc:audit-investigation]] {QUESTION}"

    chunks = await post(
        app,
        owner.user_id,
        in_memory_jobs,
        chat_post_body(owner.conversation_id, prompt),
    )

    assert called(chunks) == ["classify_user_intent", "investigate_gene_models"]
    assert text(chunks) == (
        f"The check reads the model of [{STRAIN}]"
        f"({gene_record_url('plasmodb', STRAIN)}) as intact."
    )
    assert corrections == [0]
    (stored,) = await conversation_verdicts(owner.conversation_id, owner.user_id)
    assert stored.origin == "lead"
