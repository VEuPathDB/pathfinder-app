"""Run one library check tool the way an investigation runs it, on synthetic genes."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from veupathdb_mcp.audit import GeneId, PseudogeneCallAudit

from pathfinder.ai.audit.check_tools import CHECK_TOOL_NAMES, build_check_toolset
from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.capabilities.site_reads import SiteReadFailures
from pathfinder.services.audit import investigation
from pathfinder.services.gene_records.genome import genome_of
from pathfinder.tests._support.audit_model_wire import recorded_gene_record

STRAIN = "EXA_0001"
RESOLVED = "EXA_0001:pseudogene"
REFERENCE = "EXR_0001"
PAIR_ARGS = {"strain_gene": STRAIN, "reference_gene": REFERENCE}


def intact() -> PseudogeneCallAudit:
    return PseudogeneCallAudit(
        verdict="INTACT",
        reference_cds_length=900,
        strain_cds_length=900,
        covered=900,
        premature_stops=[],
        residue_differences=0,
        gene_ids=[
            GeneId(given=STRAIN, resolved=RESOLVED),
            GeneId(given=REFERENCE, resolved=REFERENCE),
        ],
        strain_gene=RESOLVED,
        reference_gene=REFERENCE,
    )


GENOMES = {"EXA": "Examplea alpha A", "EXR": "Examplea alpha R"}


def serve_recorded_genomes(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    reads: list[tuple[str, str]] = []

    async def genome(site_id: str, gene: str) -> str:
        reads.append((site_id, gene))
        return genome_of(recorded_gene_record(GENOMES[gene[:3]]))

    monkeypatch.setattr(investigation, "read_gene_genome", genome)
    return reads


def check_deps() -> AuditDeps:
    return AuditDeps(site_id="plasmodb", user_id=uuid4(), conversation_id=uuid4())


def calling(tool_name: str, args: dict[str, Any]) -> FunctionModel:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        if len(messages) == 1:
            return ModelResponse(
                parts=[ToolCallPart(tool_name=tool_name, args=args, tool_call_id="c1")]
            )
        return ModelResponse(parts=[TextPart("done")])

    return FunctionModel(respond)


async def run_check(
    tool_name: str, args: dict[str, Any], deps: AuditDeps
) -> ToolReturnPart:
    agent = Agent(
        calling(tool_name, args),
        deps_type=AuditDeps,
        toolsets=[build_check_toolset()],
        capabilities=[SiteReadFailures[AuditDeps](reads=CHECK_TOOL_NAMES)],
    )
    result = await agent.run("check it", deps=deps)
    (returned,) = [
        part
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]
    return returned


def answering(monkeypatch: pytest.MonkeyPatch, error: Exception | None) -> None:
    async def answer(
        site_id: str, strain_gene: str, reference_gene: str
    ) -> PseudogeneCallAudit:
        del site_id, strain_gene, reference_gene
        if error is not None:
            raise error
        return intact()

    monkeypatch.setattr(investigation, "audit_pseudogene_call", answer)
