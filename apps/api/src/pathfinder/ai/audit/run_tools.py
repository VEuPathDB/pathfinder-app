"""The tools that plan, start and read gene-model audits, each read recorded as a fact the reply shows."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

import pydantic
from assistant_core.capabilities.refused_calls import CallRefused
from assistant_core.graph.tool_summary import count_noun, with_summary
from pydantic import Field
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn
from pydantic_ai.tools import Tool
from pydantic_ai.toolsets.function import FunctionToolset
from veupathdb.errors import WDKLoginRequiredError

from pathfinder.ai.audit.deps import FINDINGS_PER_CALL, AuditDeps
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
from pathfinder.ai.audit.held_genomes import genomes_of_the_site
from pathfinder.ai.fact_sources import warm_fact_schemas
from pathfinder.domain.audit.planning import (
    PlanAsk,
    PlanRefusal,
    PlanRequest,
    RunEstimate,
    ScopeProposal,
    same_scope,
)
from pathfinder.domain.audit.run_state import AuditOutcome
from pathfinder.domain.audit.scope import AuditScope
from pathfinder.domain.audit.verdicts import evidence_cite, finding_cite
from pathfinder.platform.audit_errors import AuditNeedsAThreadError
from pathfinder.platform.errors import NotFoundError
from pathfinder.services.audit.finding_views import (
    FindingDetail,
    FindingPage,
    FindingQuery,
    FindingView,
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


GENOME_RULE = (
    "A genome is one of the site's organism names, written in full. For gene "
    "targets alone, send genomes: [] with the same targets."
)


def _unheld_genome(name: str, suggested: tuple[str, ...]) -> str:
    unheld = f"the site holds no genome named {name}"
    if not suggested:
        return unheld
    return f"{unheld}; the organisms its words name are {', '.join(suggested)}"


def planner_refusal(proposal: ScopeProposal) -> str:
    if proposal.refusal is not None:
        return f"The planner starts no audit: {proposal.refusal}. {NOTHING_STARTED}"
    unheld = "; ".join(
        _unheld_genome(name, proposal.suggestions[name]) for name in proposal.unresolved
    )
    return f"The planner starts no audit: {unheld}. {GENOME_RULE} {NOTHING_STARTED}"


class PlanRefused(CallRefused):
    def __init__(self, refusal: PlanRefusal) -> None:
        super().__init__(refusal.sentence)
        self.refusal = refusal


def _planned(scope: AuditScope, cost: RunEstimate) -> str:
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
    the run. A request no audit can start from is refused with the reason,
    and a genome the site does not hold is refused with the organisms its
    words name. Nothing is written and nothing starts. To start the audit,
    call start_gene_model_audit with this request and the scope returned here.
    """
    proposal = await plan_gene_model_audit(ctx.deps.caller, request)
    scope, cost = proposal.scope, proposal.estimate
    if scope is None or cost is None:
        sentence = planner_refusal(proposal)
        raise PlanRefused(
            PlanRefusal(sentence=sentence, replannable=proposal.replannable)
        )
    fact = plan_fact(proposal)
    ctx.deps.facts.append(fact)
    genes = (gene for target in scope.targets for gene in target.genes)
    ctx.deps.records.extend(gene_records(ctx.deps.site_id, genes))
    read = AuditRead[ScopeProposal](answer=proposal)
    return with_summary(read, _planned(scope, cost), ctx=ctx)


async def start_gene_model_audit_tool(
    ctx: RunContext[AuditDeps], request: PlanAsk, scope: AuditScope
) -> ToolReturn[AuditRead[AuditOutcome]]:
    """Start the gene-model audit plan_gene_model_audit planned, after the researcher approves it.

    Give the request you planned with and the scope the planner returned for
    it, unchanged. The researcher sees the planner's scope and cost on a card
    and approves or declines it. A declined card starts nothing. An approved
    run works in the background, so the reply says it started and the turn
    ends; the run is read when the researcher asks.
    """
    del request
    outcome = await start_gene_model_audit(ctx.deps.caller, scope)
    fact = start_fact(outcome)
    ctx.deps.facts.append(fact)
    ctx.deps.runs.append(outcome.run_id)
    read = AuditRead[AuditOutcome](answer=outcome)
    return with_summary(read, f"Audit run {outcome.phase}", ctx=ctx)


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
    read = AuditRead[list[AuditRunSummary]](answer=runs)
    return with_summary(read, count_noun(len(runs), "audit run"), ctx=ctx)


async def read_audit_run_tool(
    ctx: RunContext[AuditDeps], run_id: UUID
) -> ToolReturn[AuditRead[AuditRunView]]:
    """Read one audit run: its stages, its genomes, its finding counts, its rates and its review."""
    view = await read_audit_run(ctx.deps.caller, run_id)
    fact = audit_run_fact(view)
    ctx.deps.facts.append(fact)
    ctx.deps.runs.append(run_id)
    ctx.deps.records.extend(gene_records(view.run.site_id, view.named_genes()))
    read = AuditRead[AuditRunView](answer=view)
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
    ctx.deps.runs.append(run_id)
    ctx.deps.records.extend(gene_records(view.run.site_id, view.named_genes()))
    read = AuditRead[AuditRunView](answer=view)
    state = "not started" if view.review is None else view.review.status
    return with_summary(read, f"Review {state}", ctx=ctx)


async def list_audit_findings_tool(
    ctx: RunContext[AuditDeps], run_id: UUID, query: FindingQuery
) -> ToolReturn[AuditRead[FindingPage]]:
    """List one page of an audit run's findings, highest impact first.

    query filters by check, genome, screened genome, sample, status, error type,
    certainty and gene target, and pages with offset and limit; an empty query lists the first page.
    """
    page = await list_audit_findings(ctx.deps.caller, run_id, query)
    fact = findings_fact(run_id, page)
    ctx.deps.facts.append(fact)
    ctx.deps.runs.append(run_id)
    genes = (gene for finding in page.findings for gene in finding.target.genes)
    ctx.deps.records.extend(gene_records(page.site_id, genes))
    for finding in page.findings:
        ctx.deps.hold_genomes(finding_genomes(finding))
    read = AuditRead[FindingPage](answer=page)
    summary = f"{len(page.findings)} of {count_noun(page.total, 'finding')}"
    return with_summary(read, summary, ctx=ctx)


def finding_genomes(finding: FindingView) -> dict[str, frozenset[str]]:
    named = {finding.genome, finding.screened_genome, finding.paired_genome}
    genomes = frozenset(g for g in named if g is not None)
    return dict.fromkeys(finding.target.genes, genomes)


def _held(
    deps: AuditDeps, run_id: UUID, detail: FindingDetail
) -> AuditRead[FindingDetail]:
    finding_id = detail.finding.id
    fact = audit_finding_fact(run_id, detail)
    deps.facts.append(fact)
    deps.runs.append(run_id)
    stored = (e.kind for e in detail.evidence if e.status == "stored")
    deps.reads |= {
        finding_cite(finding_id),
        *(evidence_cite(finding_id, kind) for kind in stored),
    }
    deps.records.extend(gene_records(detail.site_id, detail.finding.target.genes))
    deps.hold_genomes(finding_genomes(detail.finding))
    return AuditRead[FindingDetail](answer=detail)


async def read_audit_findings_tool(
    ctx: RunContext[AuditDeps],
    run_id: UUID,
    finding_ids: Annotated[
        list[int], Field(min_length=1, max_length=FINDINGS_PER_CALL)
    ],
) -> ToolReturn[list[AuditRead[FindingDetail]]]:
    """Read findings of an audit run, each with every piece of evidence the run stored for it.

    A call that names a finding the run does not hold reads none of them.
    """
    details = [
        await read_audit_finding(ctx.deps.caller, run_id, k)
        for k in dict.fromkeys(finding_ids)
    ]
    reads = [_held(ctx.deps, run_id, detail) for detail in details]
    return with_summary(reads, count_noun(len(reads), "finding"), ctx=ctx)


def _read_tools() -> list[Tool[AuditDeps]]:
    return [
        Tool(list_audit_runs_tool, name="list_audit_runs"),
        Tool(read_audit_run_tool, name="read_audit_run"),
        Tool(list_audit_findings_tool, name="list_audit_findings"),
        Tool(read_audit_findings_tool, name="read_audit_findings"),
    ]


def build_read_toolset() -> FunctionToolset[AuditDeps]:
    warm_fact_schemas()
    return FunctionToolset(_read_tools(), max_retries=3)


def build_run_toolset() -> FunctionToolset[AuditDeps]:
    warm_fact_schemas()
    return FunctionToolset(
        [
            Tool(
                plan_gene_model_audit_tool,
                name="plan_gene_model_audit",
                prepare=genomes_of_the_site,
            ),
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
