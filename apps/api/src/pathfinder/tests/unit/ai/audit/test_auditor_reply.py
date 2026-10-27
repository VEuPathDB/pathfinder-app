from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai import AgentRunResult, DeferredToolRequests, ModelRetry
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from veupathdb_mcp.audit import GeneId, PseudogeneCallAudit

from pathfinder.ai.audit.auditor import build_auditor_agent
from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.facts import check_fact, gene_records
from pathfinder.ai.audit.reply import AuditReply, hold_the_reply, reply_text
from pathfinder.ai.lead.contract_messages import unrendered_prose_message
from pathfinder.domain.reply_references import prose_faults
from pathfinder.services.gene_records.read import gene_record_url
from pathfinder.tests._support.audit_planning import faked_site
from pathfinder.tests._support.run_context import run_context_for

_STRAIN = "EXA_0001"
_REFERENCE = "EXR_0001"


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


def _deps() -> AuditDeps:
    fact = check_fact("audit_pseudogene_call", (_STRAIN, _REFERENCE), _intact())
    return AuditDeps(
        site_id="plasmodb",
        user_id=uuid4(),
        conversation_id=uuid4(),
        request="is the pseudogene call on EXA_0001 right",
        facts=[fact],
        records=gene_records("plasmodb", (_STRAIN, _REFERENCE)),
    )


def _referenced(deps: AuditDeps) -> AuditReply:
    (fact,) = deps.facts
    return AuditReply(
        prose=(
            f"The model of [record:{_STRAIN}] holds a CDS of "
            f"[stat:{fact.id}.strainCdsLength] bases."
        )
    )


def test_a_reply_renders_its_references_from_the_turns_facts() -> None:
    deps = _deps()

    rendered = reply_text(_referenced(deps), deps)

    assert rendered == (
        f"The model of [{_STRAIN}]({gene_record_url('plasmodb', _STRAIN)}) holds a "
        "CDS of 900 bases."
    )


def test_a_reply_with_references_passes_the_contract() -> None:
    deps = _deps()
    reply = _referenced(deps)

    assert hold_the_reply(run_context_for(deps), reply) == reply
    assert deps.reply_refusals == 0


def test_a_reply_that_writes_a_number_is_refused_with_its_reference() -> None:
    deps = _deps()
    written = AuditReply(prose=f"The model of [record:{_STRAIN}] holds 900 bases.")
    faults = prose_faults(written.prose, deps.turn_facts(deps.request))

    with pytest.raises(ModelRetry) as refused:
        hold_the_reply(run_context_for(deps), written)

    assert str(refused.value) == unrendered_prose_message(faults)
    assert deps.reply_refusals == 1


def test_a_reply_is_let_through_once_its_refusals_are_spent() -> None:
    deps = _deps().model_copy(update={"reply_refusals": 2})
    written = AuditReply(prose=f"The model of [record:{_STRAIN}] holds 900 bases.")

    assert hold_the_reply(run_context_for(deps), written) == written


def test_a_number_the_researcher_wrote_is_their_word() -> None:
    deps = _deps().model_copy(update={"request": "is a CDS of 900 bases right"})
    written = AuditReply(prose=f"The model of [record:{_STRAIN}] holds 900 bases.")

    assert hold_the_reply(run_context_for(deps), written) == written


def _answering(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    del messages
    (tool,) = info.output_tools
    args: dict[str, Any] = {"prose": "No audit run is stored for this thread."}
    return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=args)])


async def test_the_reply_check_is_a_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    faked_site(monkeypatch)
    agent = build_auditor_agent()

    with agent.override(model=FunctionModel(_answering)):
        result: AgentRunResult[AuditReply | DeferredToolRequests] = await agent.run(
            "how is the audit doing",
            deps=_deps(),
            output_type=[AuditReply, DeferredToolRequests],
        )

    assert result.output == AuditReply(prose="No audit run is stored for this thread.")
