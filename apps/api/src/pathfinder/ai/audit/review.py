"""The reviewer: one bounded agent run per stored finding, and the loop that reviews a finished audit run."""

from __future__ import annotations

from time import monotonic
from typing import Any

from assistant_core.cost import cost_for_run
from assistant_core.models.capture import maybe_wrap_model
from assistant_core.platform.db import async_session_factory
from assistant_core.quota import accumulate
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.models import Model, infer_model
from pydantic_ai.toolsets import AbstractToolset, CombinedToolset
from pydantic_ai.usage import RunUsage, UsageLimits

from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.instructions import REVIEWER_INSTRUCTIONS
from pathfinder.ai.audit.mock import build_review_mock
from pathfinder.ai.audit.retrievals import AuditRetrievalToolset
from pathfinder.ai.audit.verdict_tool import unheld_cites_message
from pathfinder.ai.capabilities.screened_sources import screened_sources
from pathfinder.domain.audit.verdicts import (
    FindingReview,
    GeneModelVerdict,
    ReviewProgress,
    ReviewStatus,
    evidence_cite,
    finding_cite,
)
from pathfinder.platform.errors import ProviderKeyError
from pathfinder.platform.model_keys import is_mock_deployment, keyed_model, turn_paid_by
from pathfinder.platform.refusals import agent_capabilities
from pathfinder.platform.tiers import REVIEW_ROLE
from pathfinder.platform.tool_sources import RESEARCH_TOOL_SOURCE
from pathfinder.services.audit import units
from pathfinder.services.audit.finding_views import FindingDetail
from pathfinder.services.audit.reviews import (
    ReviewedRun,
    agreement_sample,
    continue_review,
    next_unreviewed,
    reviewed_count,
    set_progress,
    store_review,
)
from pathfinder.services.turn_payment import turn_payment

REVIEW_LIMITS = UsageLimits(request_limit=6, tool_calls_limit=4)
REVIEW_STOPPED = "The review stopped at its budget before it reached a verdict."
BUDGET_USED = "the monthly budget is used"
NOT_SEARCHED = (
    "No literature source was open for this review, so already_known is "
    "not_searched and known_from is empty."
)


class ReviewDeps(AuditDeps):
    genes: frozenset[str] = frozenset()


def _review_sources(ctx: RunContext[ReviewDeps]) -> AbstractToolset[Any] | None:
    return ctx.deps.tool_sources


def _reviewable(ctx: RunContext[ReviewDeps], output: FindingReview) -> FindingReview:
    held = ctx.deps.held_reads()
    unheld = [
        *output.verdict.unheld_cites(held),
        *(source for source in output.known_from if source not in held),
    ]
    if unheld:
        raise ModelRetry(unheld_cites_message(unheld))
    outside = [gene for gene in output.verdict.genes if gene not in ctx.deps.genes]
    if outside:
        msg = (
            f"These genes are not the finding's: {', '.join(outside)}. Judge only "
            f"the genes of its target: {', '.join(sorted(ctx.deps.genes))}."
        )
        raise ModelRetry(msg)
    if ctx.deps.tool_sources is None and output.already_known != "not_searched":
        raise ModelRetry(NOT_SEARCHED)
    return output


def build_reviewer_agent() -> Agent[ReviewDeps, FindingReview]:
    agent = Agent(
        output_type=FindingReview,
        deps_type=ReviewDeps,
        instructions=REVIEWER_INSTRUCTIONS,
        toolsets=[_review_sources],
        capabilities=agent_capabilities([]),
        retries=3,
        name=REVIEW_ROLE,
        defer_model_check=True,
    )
    agent.output_validator(_reviewable)
    return agent


def review_deps(
    run: ReviewedRun, detail: FindingDetail, research: AbstractToolset[Any] | None
) -> ReviewDeps:
    finding = detail.finding
    stored = (e.kind for e in detail.evidence if e.status == "stored")
    return ReviewDeps(
        site_id=run.site_id,
        user_id=run.user_id,
        conversation_id=run.conversation_id,
        origin="review",
        tool_sources=research,
        reads={
            finding_cite(finding.id),
            *(evidence_cite(finding.id, kind) for kind in stored),
        },
        genes=frozenset(finding.target.genes),
    )


def _stopped(detail: FindingDetail) -> FindingReview:
    finding = detail.finding
    return FindingReview(
        verdict=GeneModelVerdict(
            genes=finding.target.genes,
            model_genome=finding.genome,
            verdict="undecided",
            cause=REVIEW_STOPPED,
            cites=(finding_cite(finding.id),),
        ),
        already_known="not_searched",
        card_text=REVIEW_STOPPED,
    )


async def review_finding(
    detail: FindingDetail, *, deps: ReviewDeps, model: Model
) -> tuple[FindingReview, RunUsage]:
    usage = RunUsage()
    try:
        result = await build_reviewer_agent().run(
            detail.model_dump_json(by_alias=True),
            deps=deps,
            model=model,
            usage=usage,
            usage_limits=REVIEW_LIMITS,
        )
    except UsageLimitExceeded, UnexpectedModelBehavior:
        return _stopped(detail), usage
    return result.output, usage


def review_model(model_id: str) -> Model:
    if is_mock_deployment():
        return build_review_mock()
    return infer_model(maybe_wrap_model(keyed_model(model_id), REVIEW_ROLE))


async def _charge(
    run: ReviewedRun, usage: RunUsage, model: Model, model_id: str
) -> None:
    cost = cost_for_run(
        usage=usage,
        model_name=model.model_name,
        provider_name=model.system,
        provider_url=model.base_url,
    )
    async with async_session_factory() as session:
        await accumulate(
            session,
            user_id=run.user_id,
            tokens=usage.total_tokens,
            cost_usd=cost,
            paid_by=turn_paid_by(model_id),
        )
        await session.commit()


class _Reviewer:
    def __init__(
        self, run: ReviewedRun, model_id: str, research: AbstractToolset[Any] | None
    ) -> None:
        self.run = run
        self.model_id = model_id
        self.model = review_model(model_id)
        self.research = research

    async def judged(self, detail: FindingDetail) -> FindingReview:
        review, usage = await review_finding(
            detail,
            deps=review_deps(self.run, detail, self.research),
            model=self.model,
        )
        await _charge(self.run, usage, self.model, self.model_id)
        return review

    async def budget_used(self) -> bool:
        async with async_session_factory() as session:
            payment = await turn_payment(session, self.run.user_id, [self.model_id])
        return payment.budget is not None


async def _progress(run: ReviewedRun, status: ReviewStatus, message: str = "") -> None:
    done = await reviewed_count(run.run_id)
    await set_progress(
        run.run_id,
        ReviewProgress(status=status, done=done, total=run.total, message=message),
    )


async def _review_all(reviewer: _Reviewer, started: float) -> None:
    run = reviewer.run
    sample = await agreement_sample(run)
    while (detail := await next_unreviewed(run.run_id, run.user_id)) is not None:
        if await reviewer.budget_used():
            await _progress(run, "stopped", BUDGET_USED)
            return
        review = await reviewer.judged(detail)
        if detail.finding.id in sample:
            second = await reviewer.judged(detail)
            review = review.model_copy(
                update={"second_verdict": second.verdict.verdict}
            )
        await store_review(run, detail.finding.id, review, reviewer.model.model_name)
        await _progress(run, "reviewing")
        if monotonic() - started >= units.SLICE_SECONDS:
            await continue_review(run.run_id)
            return
    await _progress(run, "synthesized")


async def review_until_done(run: ReviewedRun, *, model_id: str, started: float) -> None:
    async with screened_sources((RESEARCH_TOOL_SOURCE,)) as resolved:
        sources = list(resolved.by_name.values())
        research = AuditRetrievalToolset(CombinedToolset(sources)) if sources else None
        try:
            await _review_all(_Reviewer(run, model_id, research), started)
        except ProviderKeyError as refused:
            await _progress(run, "stopped", refused.title)
