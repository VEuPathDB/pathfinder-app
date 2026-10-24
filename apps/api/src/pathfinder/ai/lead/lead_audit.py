from __future__ import annotations

from typing import Annotated
from uuid import UUID

from langgraph.config import get_stream_writer
from pydantic import Field
from pydantic_ai import DeferredToolRequests, RunContext
from pydantic_ai.messages import ToolReturn
from pydantic_ai.tools import DeferredToolResults, Tool, ToolDefinition

from pathfinder.ai.audit.deps import FINDINGS_PER_CALL, AuditDeps
from pathfinder.ai.audit.facts import AuditRead
from pathfinder.ai.audit.investigator import GeneModelInvestigation
from pathfinder.ai.audit.run_tools import (
    START_TOOL,
    audit_can_start,
    build_run_toolset,
    list_audit_findings_tool,
    list_audit_runs_tool,
    plan_gene_model_audit_tool,
    read_audit_findings_tool,
    read_audit_run_tool,
    review_audit_run_tool,
    start_gene_model_audit_tool,
)
from pathfinder.ai.audit.start_card import ask_about_the_audits
from pathfinder.ai.lead.card_reply import CardReply
from pathfinder.ai.lead.dispatch_context import inner_context
from pathfinder.ai.lead.intent_gate import turn_reads_audits
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import gene_model_investigation
from pathfinder.domain.audit.findings import AuditOutcome
from pathfinder.domain.audit.planning import PlanAsk, ScopeProposal
from pathfinder.domain.audit.scope import AuditScope
from pathfinder.services.audit.finding_views import (
    FindingDetail,
    FindingPage,
    FindingQuery,
)
from pathfinder.services.audit.views import AuditRunSummary, AuditRunView


def _audit_context(ctx: RunContext[LeadDeps]) -> RunContext[AuditDeps]:
    deps = ctx.deps
    return RunContext(
        deps=AuditDeps(
            site_id=deps.site_id,
            user_id=deps.user_id,
            conversation_id=deps.conversation_id,
            origin="lead",
        ),
        model=ctx.model,
        usage=ctx.usage,
        tool_call_id=ctx.tool_call_id,
        tool_call_approved=ctx.tool_call_approved,
    )


def _keep(ctx: RunContext[LeadDeps], audit: RunContext[AuditDeps]) -> None:
    markers = ctx.deps.state.turn_markers
    markers.record_audit_facts(audit.deps.facts)
    markers.record_audit_runs(audit.deps.runs)
    for record in audit.deps.records:
        markers.record_read(record)


async def plan_gene_model_audit(
    ctx: RunContext[LeadDeps], request: PlanAsk
) -> ToolReturn[AuditRead[ScopeProposal]]:
    audit = _audit_context(ctx)
    read = await plan_gene_model_audit_tool(audit, request)
    _keep(ctx, audit)
    return read


async def start_gene_model_audit(
    ctx: RunContext[LeadDeps],
    *,
    reply: CardReply,
    request: PlanAsk,
    scope: AuditScope,
) -> ToolReturn[AuditRead[AuditOutcome]]:
    del reply
    audit = _audit_context(ctx)
    started = await start_gene_model_audit_tool(audit, request, scope)
    _keep(ctx, audit)
    return started


async def lead_audit_can_start(
    ctx: RunContext[LeadDeps],
    *,
    reply: CardReply,
    request: PlanAsk,
    scope: AuditScope,
) -> None:
    del reply
    await audit_can_start(_audit_context(ctx), request, scope)


async def list_audit_runs(
    ctx: RunContext[LeadDeps],
) -> ToolReturn[AuditRead[list[AuditRunSummary]]]:
    audit = _audit_context(ctx)
    read = await list_audit_runs_tool(audit)
    _keep(ctx, audit)
    return read


async def read_audit_run(
    ctx: RunContext[LeadDeps], run_id: UUID
) -> ToolReturn[AuditRead[AuditRunView]]:
    audit = _audit_context(ctx)
    read = await read_audit_run_tool(audit, run_id)
    _keep(ctx, audit)
    return read


async def review_audit_run(
    ctx: RunContext[LeadDeps], run_id: UUID
) -> ToolReturn[AuditRead[AuditRunView]]:
    audit = _audit_context(ctx)
    read = await review_audit_run_tool(audit, run_id)
    _keep(ctx, audit)
    return read


async def list_audit_findings(
    ctx: RunContext[LeadDeps], run_id: UUID, query: FindingQuery
) -> ToolReturn[AuditRead[FindingPage]]:
    audit = _audit_context(ctx)
    read = await list_audit_findings_tool(audit, run_id, query)
    _keep(ctx, audit)
    return read


async def read_audit_findings(
    ctx: RunContext[LeadDeps],
    run_id: UUID,
    finding_ids: Annotated[
        list[int], Field(min_length=1, max_length=FINDINGS_PER_CALL)
    ],
) -> ToolReturn[list[AuditRead[FindingDetail]]]:
    audit = _audit_context(ctx)
    read = await read_audit_findings_tool(audit, run_id, finding_ids)
    _keep(ctx, audit)
    return read


async def investigate_gene_models(
    ctx: RunContext[LeadDeps], question: str
) -> ToolReturn[GeneModelInvestigation]:
    return await gene_model_investigation.investigate_gene_models(
        inner_context(ctx), question, origin="lead"
    )


async def ask_about_the_audits_on_the_lead(
    ctx: RunContext[LeadDeps], requests: DeferredToolRequests
) -> DeferredToolResults | None:
    if all(call.tool_name != START_TOOL for call in requests.approvals):
        return None
    return await ask_about_the_audits(
        requests, get_stream_writer(), site_id=ctx.deps.site_id
    )


async def offered_on_audit_turns(
    ctx: RunContext[LeadDeps], tool_def: ToolDefinition
) -> ToolDefinition | None:
    return tool_def if turn_reads_audits(ctx.deps) else None


def lead_audit_tools() -> list[Tool[LeadDeps]]:
    described = build_run_toolset().tools

    def about(name: str) -> str | None:
        return described[name].description

    return [
        Tool(
            plan_gene_model_audit,
            prepare=offered_on_audit_turns,
            description=about("plan_gene_model_audit"),
        ),
        Tool(
            list_audit_runs,
            prepare=offered_on_audit_turns,
            description=about("list_audit_runs"),
        ),
        Tool(
            read_audit_run,
            prepare=offered_on_audit_turns,
            description=about("read_audit_run"),
        ),
        Tool(
            review_audit_run,
            prepare=offered_on_audit_turns,
            description=about("review_audit_run"),
        ),
        Tool(
            list_audit_findings,
            prepare=offered_on_audit_turns,
            description=about("list_audit_findings"),
        ),
        Tool(
            read_audit_findings,
            prepare=offered_on_audit_turns,
            description=about("read_audit_findings"),
        ),
        Tool(
            start_gene_model_audit,
            requires_approval=True,
            args_validator=lead_audit_can_start,
            prepare=offered_on_audit_turns,
            description=about(START_TOOL),
        ),
        Tool(
            investigate_gene_models,
            prepare=offered_on_audit_turns,
            description=gene_model_investigation.INVESTIGATION_DESCRIPTION,
        ),
    ]
