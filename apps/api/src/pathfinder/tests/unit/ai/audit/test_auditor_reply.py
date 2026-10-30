from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic_ai import AgentRunResult, DeferredToolRequests, ModelRetry
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from veupathdb_mcp.audit import GeneId, PseudogeneCallAudit

from pathfinder.ai.audit.auditor import build_auditor_agent
from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.facts import audit_finding_fact, check_fact, gene_records
from pathfinder.ai.audit.reply import AuditReply, hold_the_reply, reply_text
from pathfinder.ai.lead.contract_messages import note_facts_message
from pathfinder.domain.written_links import plain_markdown
from pathfinder.services.audit.finding_views import FindingDetail
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


_FINDING = json.loads(
    (
        Path(__file__).parents[3] / "fixtures/turns/fungidb_audit_finding_read.json"
    ).read_text()
)
_GENE = "Afu2g18040"


def _finding_deps() -> AuditDeps:
    detail = FindingDetail.model_validate(_FINDING["answer"])
    return AuditDeps(
        site_id="fungidb",
        user_id=uuid4(),
        conversation_id=uuid4(),
        request="is finding 1 of my audit right",
        facts=[audit_finding_fact(UUID(_FINDING["run_id"]), detail)],
        records=gene_records("fungidb", [_GENE]),
    )


def test_the_reply_shows_the_finding_before_its_note() -> None:
    deps = _finding_deps()
    note = AuditReply(
        prose=f"The review keeps the shifted splice site of [record:{_GENE}]."
    )

    shown = reply_text(note, deps).split("\n\n")

    assert (shown[0].splitlines()[:1], shown[1]) == (
        [f"**{plain_markdown('Finding 1 of audit run ' + _FINDING['run_id'])}**"],
        (
            f"The review keeps the shifted splice site of "
            f"[{_GENE}]({gene_record_url('fungidb', _GENE)})\\."
        ),
    )
    assert {"- finding certainty: medium", "- evidence kind: confirmation"} <= set(
        shown[0].splitlines()
    )


def test_a_note_without_a_number_passes_the_contract() -> None:
    deps = _deps()
    reply = AuditReply(
        prose=f"The check reads the model of [record:{_STRAIN}] as intact."
    )

    assert hold_the_reply(run_context_for(deps), reply) == reply
    assert deps.reply_refusals == 0


def test_a_note_that_writes_a_number_of_the_turn_is_refused() -> None:
    deps = _deps()
    written = AuditReply(prose=f"The model of [record:{_STRAIN}] holds 900 bases.")

    with pytest.raises(ModelRetry) as refused:
        hold_the_reply(run_context_for(deps), written)

    assert (str(refused.value), deps.reply_refusals) == (note_facts_message(["900"]), 1)


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
