"""The tools that plan, start and read gene-model audits, each read recorded as a fact a reply references."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import pydantic
from assistant_core.capabilities.refused_calls import CallRefused
from assistant_core.graph.tool_summary import count_noun, with_summary
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn
from pydantic_ai.tools import Tool
from pydantic_ai.toolsets.function import FunctionToolset
from veupathdb.errors import WDKLoginRequiredError

from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.facts import (
    AuditRead,
    audit_finding_fact,
    audit_run_fact,
    audit_runs_fact,
    findings_fact,
    gene_records,
    plan_fact,
    start_fact,
)
from pathfinder.domain.audit.findings import AuditOutcome
from pathfinder.domain.audit.planning import (
    PlanAsk,
    PlanRequest,
    ScopeProposal,
    same_scope,
)
from pathfinder.domain.audit.scope import AuditScope
from pathfinder.domain.audit.verdicts import evidence_cite, finding_cite
from pathfinder.platform.audit_errors import AuditNeedsAThreadError
from pathfinder.platform.errors import NotFoundError
from pathfinder.services.audit.finding_views import (
    FindingDetail,
    FindingPage,
    FindingQuery,
    finding_detail,
    finding_page,
)
from pathfinder.services.audit.job import begin_run
from pathfinder.services.audit.planning import plain_problems, propose_scope
from pathfinder.services.audit.reviews import start_review
from pathfinder.services.audit.sign_in import AuditsDisabledError
from pathfinder.services.audit.verdicts import AuditCaller
from pathfinder.services.audit.views import (
    AuditRunSummary,
    AuditRunView,
    list_runs,
    run_view,
)

START_TOOL = "start_gene_model_audit"
NOTHING_STARTED = "Nothing was started and no card was shown."
_ANOTHER_SCOPE = (
    "This scope is not the one the planner computes for this request; start with "
    "the scope plan_gene_model_audit returned."
)


@contextmanager
def _found() -> Iterator[None]:
    try:
        yield
    except NotFoundError as missing:
        raise CallRefused(missing.detail or missing.title) from missing


async def plan_gene_model_audit(caller: AuditCaller, ask: PlanAsk) -> ScopeProposal:
    return await propose_scope(PlanRequest.on_site(ask, caller.site_id))


async def start_gene_model_audit(
    caller: AuditCaller, scope: AuditScope
) -> AuditOutcome:
    try:
        return await begin_run(owner=caller.owner(), scope=scope)
    except (
        AuditsDisabledError,
        WDKLoginRequiredError,
        AuditNeedsAThreadError,
    ) as refused:
        raise CallRefused(refused.detail or refused.title) from refused
    except pydantic.ValidationError as inadmissible:
        msg = f"This audit cannot start: {plain_problems(inadmissible)}."
        raise CallRefused(msg) from inadmissible


async def list_audit_runs(caller: AuditCaller) -> list[AuditRunSummary]:
    return await list_runs(caller.user_id)


async def read_audit_run(caller: AuditCaller, run_id: UUID) -> AuditRunView:
    with _found():
        return await run_view(run_id, caller.user_id)


async def list_audit_findings(
    caller: AuditCaller, run_id: UUID, query: FindingQuery
) -> FindingPage:
    with _found():
        return await finding_page(run_id, caller.user_id, query)


async def read_audit_finding(
    caller: AuditCaller, run_id: UUID, finding_id: int
) -> FindingDetail:
    with _found():
        return await finding_detail(run_id, finding_id, caller.user_id)


async def review_audit_run(caller: AuditCaller, run_id: UUID) -> AuditRunView:
    try:
        owner = caller.owner()
    except AuditNeedsAThreadError as refused:
        raise CallRefused(refused.detail or refused.title) from refused
    with _found():
        await start_review(run_id, owner)
        return await run_view(run_id, caller.user_id)


def planner_refusal(proposal: ScopeProposal) -> str:
    reason = proposal.refusal or (
        f"the site holds no genome named {', '.join(proposal.unresolved)}"
    )
    return f"The planner starts no audit: {reason}. {NOTHING_STARTED}"


def _planned(proposal: ScopeProposal) -> str:
    scope, cost = proposal.scope, proposal.estimate
    if scope is None or cost is None:
        return "No audit can start from this request"
    return (
        f"{count_noun(len(scope.genomes), 'genome')} and "
        f"{count_noun(len(scope.targets), 'gene target')}, at most "
        f"{cost.hours_at_most:g} hours"
    )


async def plan_gene_model_audit_tool(
    ctx: RunContext[AuditDeps], request: PlanAsk
) -> ToolReturn[AuditRead[ScopeProposal]]:
    """Plan a gene-model audit on this conversation's site, and read what it would cost.

    The planner resolves the named genomes, picks the comparison genomes and the
    species reference, keeps the gene targets the site can judge, and estimates
    the run. scope is null when no audit can start, and refusal says why;
    unresolved names the genomes the site does not hold, with suggestions.
    Nothing is written and nothing starts. To start the audit, call
    start_gene_model_audit with this request and the scope returned here.
    """
    proposal = await plan_gene_model_audit(ctx.deps.caller, request)
    fact = plan_fact(proposal)
    ctx.deps.facts.append(fact)
    targets = () if proposal.scope is None else proposal.scope.targets
    genes = (gene for target in targets for gene in target.genes)
    ctx.deps.records.extend(gene_records(ctx.deps.site_id, genes))
    read = AuditRead[ScopeProposal](answer=proposal, fact_id=fact.id)
    return with_summary(read, _planned(proposal), ctx=ctx)


async def start_gene_model_audit_tool(
    ctx: RunContext[AuditDeps], request: PlanAsk, scope: AuditScope
) -> ToolReturn[AuditRead[AuditOutcome]]:
    """Start the gene-model audit plan_gene_model_audit planned, after the researcher approves it.

    Give the request you planned with and the scope the planner returned for
    it, unchanged. The researcher sees the planner's scope and cost on a card
    and approves or declines it. A declined card starts nothing.
    """
    del request
    outcome = await start_gene_model_audit(ctx.deps.caller, scope)
    fact = start_fact(outcome)
    ctx.deps.facts.append(fact)
    read = AuditRead[AuditOutcome](answer=outcome, fact_id=fact.id)
    return with_summary(read, f"Audit run {outcome.status}", ctx=ctx)


async def audit_can_start(
    ctx: RunContext[AuditDeps], request: PlanAsk, scope: AuditScope
) -> None:
    if ctx.tool_call_approved:
        return
    fresh = await propose_scope(PlanRequest.on_site(request, ctx.deps.site_id))
    if fresh.scope is None:
        raise ModelRetry(planner_refusal(fresh))
    if not same_scope(scope, fresh.scope):
        msg = f"{_ANOTHER_SCOPE} {NOTHING_STARTED}"
        raise ModelRetry(msg)


async def list_audit_runs_tool(
    ctx: RunContext[AuditDeps],
) -> ToolReturn[AuditRead[list[AuditRunSummary]]]:
    """List the researcher's gene-model audit runs, newest first, with each run's status."""
    runs = await list_audit_runs(ctx.deps.caller)
    fact = audit_runs_fact(runs)
    ctx.deps.facts.append(fact)
    read = AuditRead[list[AuditRunSummary]](answer=runs, fact_id=fact.id)
    return with_summary(read, count_noun(len(runs), "audit run"), ctx=ctx)


async def read_audit_run_tool(
    ctx: RunContext[AuditDeps], run_id: UUID
) -> ToolReturn[AuditRead[AuditRunView]]:
    """Read one audit run: its stages, its genomes, its finding counts, its rates and its review."""
    view = await read_audit_run(ctx.deps.caller, run_id)
    fact = audit_run_fact(view)
    ctx.deps.facts.append(fact)
    read = AuditRead[AuditRunView](answer=view, fact_id=fact.id)
    return with_summary(read, f"Audit run {view.run.status}", ctx=ctx)


async def review_audit_run_tool(
    ctx: RunContext[AuditDeps], run_id: UUID
) -> ToolReturn[AuditRead[AuditRunView]]:
    """Start or resume the review of a finished audit run's findings, and read the run.

    The review judges each confirmed finding once, highest impact first, up to
    the review cap of a run. A finding already reviewed is not reviewed again.
    Nothing starts while the run or its review is working, or when the review
    already finished with no finding left. The run's review field holds the
    progress.
    """
    view = await review_audit_run(ctx.deps.caller, run_id)
    fact = audit_run_fact(view)
    ctx.deps.facts.append(fact)
    read = AuditRead[AuditRunView](answer=view, fact_id=fact.id)
    state = "not started" if view.review is None else view.review.status
    return with_summary(read, f"Review {state}", ctx=ctx)


async def list_audit_findings_tool(
    ctx: RunContext[AuditDeps], run_id: UUID, query: FindingQuery
) -> ToolReturn[AuditRead[FindingPage]]:
    """List one page of an audit run's findings, highest impact first.

    query filters by check, genome, screened genome, sample, status and error
    type, and pages with offset and limit; an empty query lists the first page.
    """
    page = await list_audit_findings(ctx.deps.caller, run_id, query)
    fact = findings_fact(run_id, page)
    ctx.deps.facts.append(fact)
    genes = (gene for finding in page.findings for gene in finding.target.genes)
    ctx.deps.records.extend(gene_records(page.site_id, genes))
    read = AuditRead[FindingPage](answer=page, fact_id=fact.id)
    summary = f"{len(page.findings)} of {count_noun(page.total, 'finding')}"
    return with_summary(read, summary, ctx=ctx)


async def read_audit_finding_tool(
    ctx: RunContext[AuditDeps], run_id: UUID, finding_id: int
) -> ToolReturn[AuditRead[FindingDetail]]:
    """Read one finding of an audit run with every piece of evidence the run stored for it."""
    detail = await read_audit_finding(ctx.deps.caller, run_id, finding_id)
    fact = audit_finding_fact(run_id, detail)
    ctx.deps.facts.append(fact)
    stored = (e.kind for e in detail.evidence if e.status == "stored")
    ctx.deps.reads |= {
        finding_cite(finding_id),
        *(evidence_cite(finding_id, kind) for kind in stored),
    }
    ctx.deps.records.extend(gene_records(detail.site_id, detail.finding.target.genes))
    read = AuditRead[FindingDetail](answer=detail, fact_id=fact.id)
    summary = f"Finding {finding_id}: {detail.finding.status}"
    return with_summary(read, summary, ctx=ctx)


def _read_tools() -> list[Tool[AuditDeps]]:
    return [
        Tool(list_audit_runs_tool, name="list_audit_runs"),
        Tool(read_audit_run_tool, name="read_audit_run"),
        Tool(list_audit_findings_tool, name="list_audit_findings"),
        Tool(read_audit_finding_tool, name="read_audit_finding"),
    ]


def build_read_toolset() -> FunctionToolset[AuditDeps]:
    return FunctionToolset(_read_tools(), max_retries=3)


def build_run_toolset() -> FunctionToolset[AuditDeps]:
    return FunctionToolset(
        [
            Tool(plan_gene_model_audit_tool, name="plan_gene_model_audit"),
            Tool(
                start_gene_model_audit_tool,
                name=START_TOOL,
                requires_approval=True,
                args_validator=audit_can_start,
            ),
            Tool(review_audit_run_tool, name="review_audit_run"),
            *_read_tools(),
        ],
        max_retries=3,
    )


READ_TOOL_NAMES: frozenset[str] = frozenset(build_read_toolset().tools)
