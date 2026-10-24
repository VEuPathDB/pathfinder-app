from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage, UsageLimits

from pathfinder.ai.audit.facts import audit_run_fact
from pathfinder.ai.audit.instructions import SYNTHESIS_INSTRUCTIONS
from pathfinder.ai.lead.contract_messages import unrendered_prose_message
from pathfinder.domain.audit.verdicts import (
    MAX_CARD,
    GeneModelVerdict,
    ReviewAgreement,
    StoredSynthesis,
    SynthesisDraft,
    review_agreement,
)
from pathfinder.domain.reply_notes import referenced_facts
from pathfinder.domain.reply_references import nested_text, prose_faults
from pathfinder.domain.statistic_facts import StatisticFact, statistic_id
from pathfinder.domain.statistic_rows import model_rows
from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.platform.refusals import agent_capabilities
from pathfinder.platform.tiers import REVIEW_ROLE
from pathfinder.services.audit.verdicts import VerdictView
from pathfinder.services.audit.views import AuditRunView

SYNTHESIS_LIMITS = UsageLimits(request_limit=4, tool_calls_limit=0)
NO_FINDING_KEPT = "The review kept no finding of this run as an error."


class KeptFinding(CamelModel):
    model_config = ConfigDict(frozen=True)

    finding_id: int
    verdict: GeneModelVerdict
    impact: float | None


class SynthesisCounts(CamelModel):
    model_config = ConfigDict(frozen=True)

    kept: int
    rejected: int
    undecided: int
    kept_genomes: int
    genomes: int
    agreement: ReviewAgreement


class SynthesisPrompt(CamelModel):
    model_config = ConfigDict(frozen=True)

    run: AuditRunView
    kept_findings: tuple[KeptFinding, ...]
    counts: SynthesisCounts
    run_fact: str
    counts_fact: str


@dataclass(frozen=True)
class SynthesisDeps:
    kept: Mapping[int, KeptFinding]
    facts: TurnFacts


class SynthesisStoppedError(Exception):
    pass


def kept_findings(
    reviews: Sequence[VerdictView], impacts: Mapping[int, float | None]
) -> list[KeptFinding]:
    return [
        KeptFinding(
            finding_id=view.finding_id,
            verdict=view.verdict,
            impact=impacts[view.finding_id]
            if view.review is None or view.review.impact is None
            else view.review.impact,
        )
        for view in reviews
        if view.finding_id is not None and view.verdict.verdict == "error"
    ]


def synthesis_counts_fact(view: AuditRunView, counts: SynthesisCounts) -> StatisticFact:
    return StatisticFact(
        id=statistic_id("audit_synthesis", [str(view.run.id)]),
        kind="audit_synthesis",
        title=f"The reviews of audit run {view.run.id}",
        rows=model_rows(counts),
    )


def _ids(ids: Sequence[int]) -> str:
    return ", ".join(str(finding_id) for finding_id in ids)


def _rank(impact: float | None) -> float:
    return -1.0 if impact is None else impact


def _unkept(draft: SynthesisDraft, kept: Mapping[int, KeptFinding]) -> str | None:
    named = [f for section in draft.sections for f in section.finding_ids]
    outside = [f for f in dict.fromkeys(named) if f not in kept]
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
    if ordered == list(draft.headline):
        return None
    return (
        "The headline is not in descending order of impact. Order it so: "
        f"{_ids(ordered)}."
    )


def _synthesizable(
    ctx: RunContext[SynthesisDeps], output: SynthesisDraft
) -> SynthesisDraft:
    kept = ctx.deps.kept
    problem = (
        _unkept(output, kept) or _mistyped(output, kept) or _misordered(output, kept)
    )
    if problem is not None:
        raise ModelRetry(problem)
    faults = prose_faults(output.summary, ctx.deps.facts)
    if faults:
        raise ModelRetry(unrendered_prose_message(faults))
    shown = len(nested_text(output.summary, ctx.deps.facts))
    if shown > MAX_CARD:
        msg = (
            f"The summary reads {shown} characters once its references render, "
            f"more than {MAX_CARD}: shorten it, or cite fewer stored sentences."
        )
        raise ModelRetry(msg)
    return output


def build_synthesis_agent() -> Agent[SynthesisDeps, SynthesisDraft]:
    agent = Agent(
        output_type=SynthesisDraft,
        deps_type=SynthesisDeps,
        instructions=SYNTHESIS_INSTRUCTIONS,
        capabilities=agent_capabilities([]),
        retries=3,
        name=REVIEW_ROLE,
        defer_model_check=True,
    )
    agent.output_validator(_synthesizable)
    return agent


def _prompt(
    view: AuditRunView, reviews: Sequence[VerdictView], kept: Sequence[KeptFinding]
) -> tuple[SynthesisPrompt, TurnFacts]:
    verdicts = [v.verdict.verdict for v in reviews]
    counts = SynthesisCounts(
        kept=len(kept),
        rejected=verdicts.count("no_error"),
        undecided=verdicts.count("undecided"),
        kept_genomes=len({k.verdict.model_genome for k in kept}),
        genomes=len(view.run.genomes),
        agreement=review_agreement([v.review for v in reviews if v.review is not None]),
    )
    run_fact = audit_run_fact(view)
    counts_fact = synthesis_counts_fact(view, counts)
    prompt = SynthesisPrompt(
        run=view,
        kept_findings=tuple(kept),
        counts=counts,
        run_fact=run_fact.id,
        counts_fact=counts_fact.id,
    )
    return prompt, TurnFacts(statistics=[run_fact, counts_fact])


async def synthesize(
    view: AuditRunView,
    reviews: Sequence[VerdictView],
    *,
    impacts: Mapping[int, float | None],
    model: Model,
    usage: RunUsage,
    settings: ModelSettings | None = None,
) -> StoredSynthesis:
    agreement = review_agreement([v.review for v in reviews if v.review is not None])
    kept = kept_findings(reviews, impacts)
    if not kept:
        return StoredSynthesis(
            sections=(), headline=(), summary=NO_FINDING_KEPT, agreement=agreement
        )
    prompt, facts = _prompt(view, reviews, kept)
    try:
        result = await build_synthesis_agent().run(
            prompt.model_dump_json(by_alias=True),
            deps=SynthesisDeps(kept={k.finding_id: k for k in kept}, facts=facts),
            model=model,
            model_settings=settings,
            usage=usage,
            usage_limits=SYNTHESIS_LIMITS,
        )
    except (UsageLimitExceeded, UnexpectedModelBehavior) as stopped:
        raise SynthesisStoppedError from stopped
    draft = result.output
    return StoredSynthesis(
        sections=draft.sections,
        headline=draft.headline,
        summary=draft.summary,
        agreement=agreement,
        facts=referenced_facts(draft.summary, facts.cited_statistics()),
    )
