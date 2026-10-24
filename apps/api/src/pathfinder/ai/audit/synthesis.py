from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage, UsageLimits

from pathfinder.ai.audit.instructions import SYNTHESIS_INSTRUCTIONS
from pathfinder.domain.audit.verdicts import (
    GeneModelVerdict,
    ReviewAgreement,
    Synthesis,
    SynthesisDraft,
    review_agreement,
)
from pathfinder.platform.refusals import agent_capabilities
from pathfinder.platform.tiers import REVIEW_ROLE
from pathfinder.services.audit.verdicts import VerdictView
from pathfinder.services.audit.views import AuditRunView

SYNTHESIS_LIMITS = UsageLimits(request_limit=4, tool_calls_limit=0)
NO_FINDING_KEPT = "The review kept no finding of this run as an error."
SHARE_WRITTEN = (
    "The summary states a percentage or a share of the kept findings. State the "
    "counts the review kept and rejected only, and no rate of them."
)
_SHARE = re.compile(
    r"%|\bper ?cent\b|\bshare\b|\bproportion\b|\bfraction\b"
    r"|\b\d+\s*(?:/|of|out of)\s*\d+\b",
    re.IGNORECASE,
)


class KeptFinding(CamelModel):
    model_config = ConfigDict(frozen=True)

    finding_id: int
    verdict: GeneModelVerdict
    impact: float | None


class SynthesisPrompt(CamelModel):
    model_config = ConfigDict(frozen=True)

    run: AuditRunView
    kept_findings: tuple[KeptFinding, ...]
    rejected: int
    undecided: int
    agreement: ReviewAgreement


class SynthesisStoppedError(Exception):
    def __init__(self, usage: RunUsage) -> None:
        super().__init__("the synthesis stopped before it wrote a valid synthesis")
        self.usage = usage


def kept_findings(
    reviews: Sequence[VerdictView], impacts: Mapping[int, float | None]
) -> list[KeptFinding]:
    return [
        KeptFinding(
            finding_id=view.finding_id,
            verdict=view.verdict,
            impact=impacts.get(view.finding_id)
            if view.review is None or view.review.impact is None
            else view.review.impact,
        )
        for view in reviews
        if view.finding_id is not None and view.verdict.verdict == "error"
    ]


def _ids(ids: Sequence[int]) -> str:
    return ", ".join(str(finding_id) for finding_id in ids)


def _rank(impact: float | None) -> float:
    return -1.0 if impact is None else impact


def _unkept(draft: SynthesisDraft, kept: Mapping[int, KeptFinding]) -> str | None:
    named = [f for section in draft.sections for f in section.finding_ids]
    outside = [f for f in dict.fromkeys([*named, *draft.headline]) if f not in kept]
    if not outside:
        return None
    return (
        f"These findings have no review that keeps them as an error: "
        f"{_ids(outside)}. Name only the kept findings: {_ids(list(kept))}."
    )


def _mistyped(draft: SynthesisDraft, kept: Mapping[int, KeptFinding]) -> str | None:
    for section in draft.sections:
        other = [
            f"{f} ({kept[f].verdict.error_type})"
            for f in section.finding_ids
            if kept[f].verdict.error_type != section.error_type
        ]
        if other:
            return (
                f"The section {section.error_type} holds findings whose reviews "
                f"name another error type: {', '.join(other)}."
            )
    return None


def _misordered(draft: SynthesisDraft, kept: Mapping[int, KeptFinding]) -> str | None:
    ordered = sorted(draft.headline, key=lambda f: _rank(kept[f].impact), reverse=True)
    if [kept[f].impact for f in ordered] == [kept[f].impact for f in draft.headline]:
        return None
    return (
        "The headline is not in descending order of impact. Order it so: "
        f"{_ids(ordered)}."
    )


def _synthesizable(
    ctx: RunContext[SynthesisPrompt], output: SynthesisDraft
) -> SynthesisDraft:
    kept = {k.finding_id: k for k in ctx.deps.kept_findings}
    problem = (
        _unkept(output, kept) or _mistyped(output, kept) or _misordered(output, kept)
    )
    if problem is not None:
        raise ModelRetry(problem)
    if _SHARE.search(output.summary):
        raise ModelRetry(SHARE_WRITTEN)
    return output


def build_synthesis_agent() -> Agent[SynthesisPrompt, SynthesisDraft]:
    agent = Agent(
        output_type=SynthesisDraft,
        deps_type=SynthesisPrompt,
        instructions=SYNTHESIS_INSTRUCTIONS,
        capabilities=agent_capabilities([]),
        retries=3,
        name=REVIEW_ROLE,
        defer_model_check=True,
    )
    agent.output_validator(_synthesizable)
    return agent


async def synthesize(
    view: AuditRunView,
    reviews: Sequence[VerdictView],
    *,
    impacts: Mapping[int, float | None],
    model: Model,
    settings: ModelSettings | None = None,
) -> tuple[Synthesis, RunUsage]:
    agreement = review_agreement([v.review for v in reviews if v.review is not None])
    kept = kept_findings(reviews, impacts)
    usage = RunUsage()
    if not kept:
        empty = Synthesis(
            sections=(), headline=(), summary=NO_FINDING_KEPT, agreement=agreement
        )
        return empty, usage
    verdicts = [v.verdict.verdict for v in reviews]
    prompt = SynthesisPrompt(
        run=view,
        kept_findings=tuple(kept),
        rejected=verdicts.count("no_error"),
        undecided=verdicts.count("undecided"),
        agreement=agreement,
    )
    try:
        result = await build_synthesis_agent().run(
            prompt.model_dump_json(by_alias=True),
            deps=prompt,
            model=model,
            model_settings=settings,
            usage=usage,
            usage_limits=SYNTHESIS_LIMITS,
        )
    except (UsageLimitExceeded, UnexpectedModelBehavior) as stopped:
        raise SynthesisStoppedError(usage) from stopped
    draft = result.output
    synthesis = Synthesis(
        sections=draft.sections,
        headline=draft.headline,
        summary=draft.summary,
        agreement=agreement,
    )
    return synthesis, usage
