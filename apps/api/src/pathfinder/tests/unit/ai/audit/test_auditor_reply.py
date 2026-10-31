from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic_ai import AgentRunResult, DeferredToolRequests
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from veupathdb_mcp.audit import GeneId, PseudogeneCallAudit

from pathfinder.ai.audit.auditor import build_auditor_agent
from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.facts import audit_finding_fact, check_fact, gene_records
from pathfinder.ai.audit.reply import AuditReply, reply_text
from pathfinder.domain.written_links import plain_markdown
from pathfinder.services.audit.finding_views import FindingDetail
from pathfinder.services.gene_records.read import gene_record_url
from pathfinder.tests._support.audit_planning import faked_site

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


def _answering(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    del messages
    (tool,) = info.output_tools
    args: dict[str, Any] = {"prose": "No audit run is stored for this thread."}
    return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=args)])


async def test_the_auditor_answers_with_its_typed_reply(
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
