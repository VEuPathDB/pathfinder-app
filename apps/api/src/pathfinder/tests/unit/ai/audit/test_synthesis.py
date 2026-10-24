from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.models.scripted import retry_prompt_parts, terminal_call, user_texts
from pydantic_ai.messages import ModelMessage, ModelResponse, RetryPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pathfinder.ai.audit.mock import build_synthesis_mock
from pathfinder.ai.audit.synthesis import (
    NO_FINDING_KEPT,
    SHARE_WRITTEN,
    SYNTHESIS_LIMITS,
    KeptFinding,
    SynthesisStoppedError,
    kept_findings,
    synthesize,
)
from pathfinder.domain.audit.findings import ErrorType
from pathfinder.domain.audit.rates import TargetReport
from pathfinder.domain.audit.run_state import LeftUnits
from pathfinder.domain.audit.scope import AuditScope, SingleGeneTarget
from pathfinder.domain.audit.stages import RunStages
from pathfinder.domain.audit.verdicts import (
    ErrorTypeSection,
    FindingReview,
    GeneModelVerdict,
    ReviewAgreement,
    Synthesis,
    VerdictKind,
    finding_cite,
)
from pathfinder.services.audit.verdicts import VerdictView
from pathfinder.services.audit.views import AuditRunSummary, AuditRunView

_GENOME = "Examplea alpha A"
_NOW = datetime(2026, 10, 24, tzinfo=UTC)
_TRUNCATED: ErrorType = "truncated_model"
_SPLIT: ErrorType = "split_model"


def _view() -> AuditRunView:
    run_id = uuid4()
    return AuditRunView(
        run=AuditRunSummary(
            id=run_id,
            site_id="plasmodb",
            conversation_id=None,
            release=None,
            status="finished",
            phase="finished",
            deadline_at=None,
            genomes=[],
            checks=["gene_length"],
            targets=1,
            created_at=_NOW,
            finished_at=_NOW,
        ),
        scope=AuditScope(
            site_id="plasmodb",
            targets=(SingleGeneTarget(check="gene_length", genes=("EXA_0001",)),),
        ),
        stages=RunStages(),
        requests=0,
        store_reads=0,
        unfinished=[],
        genomes=[],
        counts=[],
        rates=[],
        targets=TargetReport(genomes=[], unplaced=0),
        review=None,
        synthesis=None,
        reviewed=0,
        action=None,
        reviews_running=False,
        halt=None,
        left=LeftUnits(genomes=0, findings=0, evidence=0),
        evidence=[],
    )


def _stored(
    finding_id: int,
    verdict: VerdictKind = "error",
    *,
    error_type: ErrorType = _TRUNCATED,
    second: VerdictKind | None = None,
    impact: float | None = None,
) -> VerdictView:
    named = verdict == "error"
    return VerdictView(
        id=finding_id,
        run_id=uuid4(),
        finding_id=finding_id,
        origin="review",
        verdict=GeneModelVerdict(
            genes=(f"EXA_{finding_id:04d}",),
            model_genome=_GENOME,
            verdict=verdict,
            error_type=error_type if named else None,
            certainty="high" if named else None,
            cause=f"The relatives of finding {finding_id} are longer.",
            cites=(finding_cite(finding_id),),
        ),
        review=FindingReview(
            verdict=GeneModelVerdict(
                genes=(f"EXA_{finding_id:04d}",),
                model_genome=_GENOME,
                verdict=verdict,
                error_type=error_type if named else None,
                certainty="high" if named else None,
                cause=f"The relatives of finding {finding_id} are longer.",
                cites=(finding_cite(finding_id),),
            ),
            already_known="not_searched",
            card_text=f"Finding {finding_id} is a synthetic model.",
            impact=impact,
            impact_reason=None if impact is None else "The reviewer weighed it.",
            second_verdict=second,
        ),
        created_at=_NOW,
    )


def _section(error_type: ErrorType, *ids: int) -> dict[str, Any]:
    return {
        "errorType": error_type,
        "cause": "The models stop early.",
        "confirmedBy": "The relatives' lengths confirm it.",
        "findingIds": list(ids),
    }


def _draft(
    sections: list[dict[str, Any]], headline: list[int], summary: str = "Two kept."
) -> dict[str, Any]:
    return {"sections": sections, "headline": headline, "summary": summary}


_RIGHT = _draft([_section(_TRUNCATED, 1, 2)], [1, 2])


def _first_then(
    wrong: dict[str, Any],
    retries: list[RetryPromptPart],
    right: dict[str, Any] = _RIGHT,
) -> FunctionModel:
    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        retries.extend(retry_prompt_parts(messages))
        return ModelResponse(parts=[terminal_call(right if retries else wrong)])

    return FunctionModel(answer)


_IMPACTS = {1: 0.9, 2: 0.5, 3: 0.7, 4: 0.2}


async def _synthesized(reviews: list[VerdictView], model: FunctionModel) -> Synthesis:
    found, _ = await synthesize(_view(), reviews, impacts=_IMPACTS, model=model)
    return found


def test_the_synthesis_limits() -> None:
    assert (SYNTHESIS_LIMITS.request_limit, SYNTHESIS_LIMITS.tool_calls_limit) == (4, 0)


def test_kept_findings_carry_the_reviews_impact_over_the_stored_one() -> None:
    reviews = [
        _stored(1, impact=0.3),
        _stored(2),
        _stored(3, "no_error"),
        _stored(4, "undecided"),
    ]

    assert kept_findings(reviews, {1: 0.9, 2: 0.5}) == [
        KeptFinding(finding_id=1, verdict=reviews[0].verdict, impact=0.3),
        KeptFinding(finding_id=2, verdict=reviews[1].verdict, impact=0.5),
    ]


def test_a_kept_finding_with_no_stored_impact_has_none() -> None:
    reviews = [_stored(5)]

    assert kept_findings(reviews, {}) == [
        KeptFinding(finding_id=5, verdict=reviews[0].verdict, impact=None)
    ]


async def test_a_section_naming_a_rejected_finding_is_retried() -> None:
    retries: list[RetryPromptPart] = []
    reviews = [_stored(1), _stored(2), _stored(3, "no_error")]
    wrong = _draft([_section(_TRUNCATED, 1, 2, 3)], [1])

    found = await _synthesized(reviews, _first_then(wrong, retries))

    assert retries[0].content == (
        "These findings have no review that keeps them as an error: 3. "
        "Name only the kept findings: 1, 2."
    )
    assert found.sections[0].finding_ids == (1, 2)


async def test_a_headline_naming_an_unreviewed_finding_is_retried() -> None:
    retries: list[RetryPromptPart] = []
    reviews = [_stored(1), _stored(2), _stored(4, "undecided")]
    wrong = _draft([_section(_TRUNCATED, 1, 2), _section(_SPLIT, 4)], [1, 4])

    await _synthesized(reviews, _first_then(wrong, retries))

    assert retries[0].content == (
        "These findings have no review that keeps them as an error: 4. "
        "Name only the kept findings: 1, 2."
    )


async def test_a_section_of_another_error_type_is_retried() -> None:
    retries: list[RetryPromptPart] = []
    reviews = [_stored(1), _stored(2, error_type=_SPLIT)]
    wrong = _draft([_section(_TRUNCATED, 1, 2)], [1, 2])
    right = _draft([_section(_TRUNCATED, 1), _section(_SPLIT, 2)], [1, 2])

    found = await _synthesized(reviews, _first_then(wrong, retries, right))

    assert retries[0].content == (
        "The section truncated_model holds findings whose reviews name another "
        "error type: 2 (split_model)."
    )
    assert [s.error_type for s in found.sections] == [_TRUNCATED, _SPLIT]


async def test_a_headline_out_of_impact_order_is_retried() -> None:
    retries: list[RetryPromptPart] = []
    reviews = [_stored(1), _stored(2), _stored(3)]
    wrong = _draft([_section(_TRUNCATED, 1, 2, 3)], [2, 1, 3])
    right = _draft([_section(_TRUNCATED, 1, 2, 3)], [1, 3, 2])

    found = await _synthesized(reviews, _first_then(wrong, retries, right))

    assert retries[0].content == (
        "The headline is not in descending order of impact. Order it so: 1, 3, 2."
    )
    assert found.headline == (1, 3, 2)


async def test_the_headline_orders_by_the_reviews_impact_and_none_last() -> None:
    retries: list[RetryPromptPart] = []
    reviews = [_stored(1, impact=0.1), _stored(2), _stored(5)]
    wrong = _draft([_section(_TRUNCATED, 1, 2, 5)], [1, 5, 2])
    right = _draft([_section(_TRUNCATED, 1, 2, 5)], [2, 1, 5])

    found = await _synthesized(reviews, _first_then(wrong, retries, right))

    assert retries[0].content == (
        "The headline is not in descending order of impact. Order it so: 2, 1, 5."
    )
    assert found.headline == (2, 1, 5)


async def test_a_headline_of_equal_impacts_is_accepted() -> None:
    retries: list[RetryPromptPart] = []
    reviews = [_stored(1, impact=0.5), _stored(2)]
    right = _draft([_section(_TRUNCATED, 1, 2)], [1, 2])

    found = await _synthesized(reviews, _first_then(right, retries))

    assert (retries, found.headline) == ([], (1, 2))


@pytest.mark.parametrize(
    "summary",
    [
        "80% of the findings were kept",
        "80 % of the findings were kept",
        "Forty percent of the findings were kept.",
        "Forty per cent of the findings were kept.",
        "Most of the share of findings was kept.",
        "A large proportion was kept.",
        "A fraction was kept.",
        "4 of 5 findings were kept.",
        "4 out of 5 findings were kept.",
        "4/5 findings were kept.",
    ],
)
async def test_a_summary_writing_a_share_of_kept_findings_is_retried(
    summary: str,
) -> None:
    retries: list[RetryPromptPart] = []
    wrong = _draft([_section(_TRUNCATED, 1, 2)], [1, 2], summary)

    found = await _synthesized([_stored(1), _stored(2)], _first_then(wrong, retries))

    assert retries[0].content == SHARE_WRITTEN
    assert found.summary == "Two kept."


async def test_a_summary_stating_counts_is_accepted() -> None:
    retries: list[RetryPromptPart] = []
    said = "The review kept 2 findings as errors and rejected 1."
    right = _draft([_section(_TRUNCATED, 1, 2)], [1, 2], said)

    found = await _synthesized(
        [_stored(1), _stored(2), _stored(3, "no_error")], _first_then(right, retries)
    )

    assert (retries, found.summary) == ([], said)


async def test_the_agreement_is_computed_from_the_reviews() -> None:
    retries: list[RetryPromptPart] = []
    reviews = [
        _stored(1, second="error"),
        _stored(2, second="no_error"),
        _stored(3, "no_error", second="no_error"),
        _stored(4, "undecided"),
    ]

    found = await _synthesized(reviews, _first_then(_RIGHT, retries))

    assert found.agreement == ReviewAgreement(sampled=3, agreed=2)
    assert found.model_dump(by_alias=True, mode="json")["agreement"] == {
        "sampled": 3,
        "agreed": 2,
        "share": 0.667,
    }


async def test_the_model_reads_the_kept_findings_and_the_counts() -> None:
    seen: list[str] = []

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        seen.extend(user_texts(messages))
        return ModelResponse(parts=[terminal_call(_RIGHT)])

    reviews = [_stored(1), _stored(2), _stored(3, "no_error"), _stored(4, "undecided")]
    await _synthesized(reviews, FunctionModel(answer))

    (prompt,) = seen
    assert '"rejected":1,"undecided":1' in prompt
    assert '"keptFindings":[{"findingId":1,' in prompt
    assert '"impact":0.9}' in prompt
    assert '"agreement":{"sampled":0,"agreed":0,"share":null}' in prompt
    assert '"run":{"run":{"id":' in prompt


async def test_no_kept_finding_makes_no_model_call() -> None:
    def refuse(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise AssertionError((messages, info))

    reviews = [_stored(3, "no_error", second="undecided"), _stored(4, "undecided")]

    found, usage = await synthesize(
        _view(), reviews, impacts=_IMPACTS, model=FunctionModel(refuse)
    )

    assert found == Synthesis(
        sections=(),
        headline=(),
        summary=NO_FINDING_KEPT,
        agreement=ReviewAgreement(sampled=1, agreed=0),
    )
    assert NO_FINDING_KEPT == "The review kept no finding of this run as an error."
    assert usage.requests == 0


async def test_a_synthesis_whose_retries_are_spent_stops() -> None:
    def always_wrong(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        return ModelResponse(parts=[terminal_call(_draft([_section(_SPLIT, 1)], [1]))])

    with pytest.raises(SynthesisStoppedError) as stopped:
        await _synthesized([_stored(1)], FunctionModel(always_wrong))

    assert stopped.value.usage.requests == 4


async def test_the_mock_synthesis_groups_the_kept_findings_by_impact() -> None:
    reviews = [
        _stored(2),
        _stored(4, error_type=_SPLIT),
        _stored(1, impact=0.1),
        _stored(3),
        _stored(6, "no_error"),
    ]

    found = await _synthesized(reviews, build_synthesis_mock())

    assert found == Synthesis(
        sections=(
            ErrorTypeSection(
                error_type=_TRUNCATED,
                cause="The relatives of finding 3 are longer.",
                confirmed_by="The stored evidence of findings 3, 2, 1 confirms it.",
                finding_ids=(3, 2, 1),
            ),
            ErrorTypeSection(
                error_type=_SPLIT,
                cause="The relatives of finding 4 are longer.",
                confirmed_by="The stored evidence of findings 4 confirms it.",
                finding_ids=(4,),
            ),
        ),
        headline=(3, 2, 4, 1),
        summary="The review kept 4 findings as errors and rejected 1.",
        agreement=ReviewAgreement(sampled=0, agreed=0),
    )
