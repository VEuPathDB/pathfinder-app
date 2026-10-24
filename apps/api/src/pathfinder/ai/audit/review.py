"""The reviewer: one bounded agent run per stored finding, and the loop that reviews a finished audit run."""

from __future__ import annotations

from time import monotonic
from typing import Any

from assistant_core.models.capture import maybe_wrap_model
from assistant_core.models.settings import build_model_settings
from assistant_core.platform.db import async_session_factory
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.models import Model, infer_model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.toolsets import AbstractToolset, CombinedToolset
from pydantic_ai.usage import RunUsage, UsageLimits

from pathfinder.ai.audit.charges import charge_run
from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.instructions import REVIEWER_INSTRUCTIONS
from pathfinder.ai.audit.mock import build_review_mock, build_synthesis_mock
from pathfinder.ai.audit.retrievals import AuditRetrievalToolset
from pathfinder.ai.audit.synthesis import (
    SynthesisStoppedError,
    kept_findings,
    synthesize,
)
from pathfinder.ai.audit.verdict_tool import unheld_cites_message
from pathfinder.ai.capabilities.screened_sources import screened_sources
from pathfinder.domain.audit.verdicts import (
    FindingReview,
    GeneModelVerdict,
    evidence_cite,
    finding_cite,
)
from pathfinder.platform.errors import ProviderKeyError
from pathfinder.platform.identity import AUDIT_ASSISTANT_ID
from pathfinder.platform.model_keys import is_mock_deployment, keyed_model
from pathfinder.platform.refusals import agent_capabilities
from pathfinder.platform.tiers import REVIEW_ROLE, deployment_role_config
from pathfinder.platform.tool_sources import RESEARCH_TOOL_SOURCE
from pathfinder.services.audit import units
from pathfinder.services.audit.finding_views import FindingDetail
from pathfinder.services.audit.reviews import (
    ReviewedRun,
    agreement_sample,
    continue_review,
    next_unreviewed,
    record_progress,
    store_review,
    store_synthesis,
    stored_impacts,
    stored_reviews,
)
from pathfinder.services.audit.views import run_view
from pathfinder.services.turn_payment import turn_payment

REVIEW_LIMITS = UsageLimits(request_limit=6, tool_calls_limit=4)
OUT_OF_LIMITS = (
    "The review stopped at its request or tool-call limit before it reached a verdict."
)
OUT_OF_RETRIES = (
    "The review stopped when its retries were spent before it wrote a valid review."
)
BUDGET_USED = "the monthly budget is used"
SYNTHESIS_STOPPED = (
    "The synthesis stopped before it wrote a valid synthesis of the reviews."
)
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


def _stopped(detail: FindingDetail, cause: str) -> FindingReview:
    finding = detail.finding
    return FindingReview(
        verdict=GeneModelVerdict(
            genes=finding.target.genes,
            model_genome=finding.genome,
            verdict="undecided",
            cause=cause,
            cites=(finding_cite(finding.id),),
        ),
        already_known="not_searched",
        card_text=cause,
        stopped=True,
    )


async def review_finding(
    detail: FindingDetail,
    *,
    deps: ReviewDeps,
    model: Model,
    settings: ModelSettings | None,
    usage: RunUsage,
) -> FindingReview:
    try:
        result = await build_reviewer_agent().run(
            detail.model_dump_json(by_alias=True, exclude={"models"}),
            deps=deps,
            model=model,
            model_settings=settings,
            usage=usage,
            usage_limits=REVIEW_LIMITS,
        )
    except UsageLimitExceeded:
        return _stopped(detail, OUT_OF_LIMITS)
    except UnexpectedModelBehavior:
        return _stopped(detail, OUT_OF_RETRIES)
    return result.output


def review_model(model_id: str) -> Model:
    if is_mock_deployment():
        return build_review_mock()
    return infer_model(maybe_wrap_model(keyed_model(model_id), REVIEW_ROLE))


def synthesis_model(model_id: str) -> Model:
    if is_mock_deployment():
        return build_synthesis_mock()
    return infer_model(maybe_wrap_model(keyed_model(model_id), REVIEW_ROLE))


def review_settings(model_id: str) -> ModelSettings:
    config = deployment_role_config(AUDIT_ASSISTANT_ID, REVIEW_ROLE)
    effort = None if config is None else config.reasoning_effort
    return build_model_settings(model_id, thinking=effort)


class _Reviewer:
    def __init__(
        self, run: ReviewedRun, model_id: str, research: AbstractToolset[Any] | None
    ) -> None:
        self.run = run
        self.model_id = model_id
        self.model = review_model(model_id)
        self.settings = review_settings(model_id)
        self.research = research

    async def judged(self, detail: FindingDetail) -> FindingReview:
        usage = RunUsage()
        try:
            return await review_finding(
                detail,
                deps=review_deps(self.run, detail, self.research),
                model=self.model,
                settings=self.settings,
                usage=usage,
            )
        finally:
            await charge_run(
                self.run.user_id, usage, self.model, model_id=self.model_id
            )

    async def budget_used(self) -> bool:
        async with async_session_factory() as session:
            payment = await turn_payment(session, self.run.user_id, [self.model_id])
        return payment.budget is not None

    async def reviewed(self, detail: FindingDetail, *, twice: bool) -> FindingReview:
        first = await self.judged(detail)
        if first.stopped or not twice:
            return first
        second = await self.judged(detail)
        if second.stopped:
            return first
        return first.model_copy(update={"second_verdict": second.verdict.verdict})


async def _review_all(reviewer: _Reviewer, started: float) -> None:
    run = reviewer.run
    sample = await agreement_sample(run)
    while (detail := await next_unreviewed(run.run_id, run.user_id)) is not None:
        if await reviewer.budget_used():
            await record_progress(run, "stopped", BUDGET_USED)
            return
        finding_id = detail.finding.id
        review = await reviewer.reviewed(detail, twice=finding_id in sample)
        await store_review(run, finding_id, review, reviewer.model.model_name)
        await record_progress(run, "reviewing")
        if monotonic() - started >= units.SLICE_SECONDS:
            await continue_review(run.run_id)
            return
    await _synthesize(reviewer)


async def _synthesize(reviewer: _Reviewer) -> None:
    run = reviewer.run
    found = await stored_reviews(run.run_id)
    impacts = await stored_impacts(run.run_id)
    if kept_findings(found, impacts) and await reviewer.budget_used():
        await record_progress(run, "stopped", BUDGET_USED)
        return
    view = await run_view(run.run_id, run.user_id)
    model = synthesis_model(reviewer.model_id)
    usage = RunUsage()
    try:
        synthesis = await synthesize(
            view,
            found,
            impacts=impacts,
            model=model,
            usage=usage,
            settings=reviewer.settings,
        )
    except SynthesisStoppedError:
        await record_progress(run, "stopped", SYNTHESIS_STOPPED)
        return
    finally:
        await charge_run(run.user_id, usage, model, model_id=reviewer.model_id)
    await store_synthesis(run.run_id, synthesis)
    await record_progress(run, "synthesized")


async def review_until_done(run: ReviewedRun, *, model_id: str, started: float) -> None:
    async with screened_sources((RESEARCH_TOOL_SOURCE,)) as resolved:
        sources = list(resolved.by_name.values())
        research = AuditRetrievalToolset(CombinedToolset(sources)) if sources else None
        try:
            await _review_all(_Reviewer(run, model_id, research), started)
        except ProviderKeyError as refused:
            await record_progress(run, "stopped", refused.title)
