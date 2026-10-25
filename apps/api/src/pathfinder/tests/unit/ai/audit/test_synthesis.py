from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from assistant_core.models.scripted import retry_prompt_parts, terminal_call, user_texts
from pydantic_ai.messages import ModelMessage, ModelResponse, RetryPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RunUsage

from pathfinder.ai.audit.facts import audit_run_fact
from pathfinder.ai.audit.mock import build_synthesis_mock
from pathfinder.ai.audit.synthesis import (
    NO_FINDING_KEPT,
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
    StoredSynthesis,
    VerdictKind,
    finding_cite,
)
from pathfinder.domain.statistic_facts import (
    StatisticFact,
    StatisticRowFact,
    statistic_id,
)
from pathfinder.services.audit.verdicts import VerdictView
from pathfinder.services.audit.views import AuditRunSummary, AuditRunView

_GENOME = "Examplea alpha A"
_OTHER = "Examplea beta B"
_NOW = datetime(2026, 10, 24, tzinfo=UTC)
_RUN = UUID("00000000-0000-4000-8000-000000000001")
_TRUNCATED: ErrorType = "truncated_model"
_SPLIT: ErrorType = "split_model"
_COUNTS = statistic_id("audit_synthesis", [str(_RUN)])


def _view(genomes: tuple[str, ...] = ()) -> AuditRunView:
    return AuditRunView(
        run=AuditRunSummary(
            id=_RUN,
            site_id="plasmodb",
            conversation_id=None,
            release=None,
            status="finished",
            phase="finished",
            deadline_at=None,
            genomes=list(genomes),
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
        error_types=[],
        headline=[],
        review_state=None,
        agreement=None,
    )


_RUN_FACT = audit_run_fact(_view()).id


def _stored(
    finding_id: int,
    verdict: VerdictKind = "error",
    *,
    error_type: ErrorType = _TRUNCATED,
    second: VerdictKind | None = None,
    impact: float | None = None,
    genome: str = _GENOME,
) -> VerdictView:
    named = verdict == "error"
    judged = GeneModelVerdict(
        genes=(f"EXA_{finding_id:04d}",),
        model_genome=genome,
        verdict=verdict,
        error_type=error_type if named else None,
        certainty="high" if named else None,
        cause=f"The relatives of EXA_{finding_id:04d} are longer.",
        cites=(finding_cite(finding_id),),
    )
    return VerdictView(
        id=finding_id,
        run_id=_RUN,
        finding_id=finding_id,
        origin="review",
        verdict=judged,
        review=FindingReview(
            verdict=judged,
            already_known="not_searched",
            card_text="A synthetic model.",
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


_IMPACTS: dict[int, float | None] = {1: 0.9, 2: 0.5, 3: 0.7, 4: 0.2, 5: None, 6: 0.1}


async def _synthesized(
    reviews: list[VerdictView],
    model: FunctionModel,
    view: AuditRunView | None = None,
) -> StoredSynthesis:
    return await synthesize(
        view or _view(), reviews, impacts=_IMPACTS, model=model, usage=RunUsage()
    )


def test_the_synthesis_limits() -> None:
    assert (SYNTHESIS_LIMITS.request_limit, SYNTHESIS_LIMITS.tool_calls_limit) == (4, 0)


def test_kept_findings_carry_the_reviews_impact_over_the_stored_one() -> None:
    reviews = [
        _stored(1, impact=0.3),
        _stored(2),
        _stored(3, "no_error"),
        _stored(4, "undecided"),
        _stored(5),
    ]

    assert kept_findings(reviews, _IMPACTS) == [
        KeptFinding(finding_id=1, verdict=reviews[0].verdict, impact=0.3),
        KeptFinding(finding_id=2, verdict=reviews[1].verdict, impact=0.5),
        KeptFinding(finding_id=5, verdict=reviews[4].verdict, impact=None),
    ]


def test_a_kept_finding_with_no_stored_impact_row_fails() -> None:
    with pytest.raises(KeyError):
        kept_findings([_stored(9)], _IMPACTS)


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


@pytest.mark.parametrize("headline", [[1, 2], [2, 1]])
async def test_a_headline_of_equal_impacts_is_accepted_in_either_order(
    headline: list[int],
) -> None:
    retries: list[RetryPromptPart] = []
    reviews = [_stored(1, impact=0.5), _stored(2)]
    right = _draft([_section(_TRUNCATED, 1, 2)], headline)

    found = await _synthesized(reviews, _first_then(right, retries))

    assert (retries, list(found.headline)) == ([], headline)


@pytest.mark.parametrize(
    ("summary", "token"),
    [
        ("80% of the findings were kept.", "80"),
        ("The review kept 2 findings.", "2"),
        (f"The review kept [stat:{_COUNTS}.keptShare] of the findings.", "keptShare"),
        ("The review kept [stat:stat_00000000.kept] findings.", "stat_00000000"),
    ],
)
async def test_a_summary_that_states_a_fact_no_fact_holds_is_retried(
    summary: str, token: str
) -> None:
    retries: list[RetryPromptPart] = []
    wrong = _draft([_section(_TRUNCATED, 1, 2)], [1, 2], summary)

    found = await _synthesized([_stored(1), _stored(2)], _first_then(wrong, retries))

    (retry,) = retries
    assert token in str(retry.content)
    assert found.summary == "Two kept."


@pytest.mark.parametrize(
    "summary",
    [
        (
            f"The kept errors lie in [stat:{_COUNTS}.keptGenomes] of "
            f"[stat:{_COUNTS}.genomes] genomes."
        ),
        (
            "Two independent reviews agreed on "
            f"[stat:{_COUNTS}.agreement.agreed] of "
            f"[stat:{_COUNTS}.agreement.sampled] sampled findings."
        ),
        (
            f"The review kept [stat:{_COUNTS}.kept] findings and rejected "
            f"[stat:{_COUNTS}.rejected], over [stat:{_RUN_FACT}.run.targets] target."
        ),
    ],
)
async def test_a_summary_of_held_facts_is_stored_as_written(summary: str) -> None:
    retries: list[RetryPromptPart] = []
    reviews = [
        _stored(1, second="error"),
        _stored(2, second="no_error", genome=_OTHER),
        _stored(3, "no_error"),
    ]
    right = _draft([_section(_TRUNCATED, 1, 2)], [1, 2], summary)
    view = _view(("Examplea alpha A", "Examplea beta B", "Examplea gamma C"))

    found = await _synthesized(reviews, _first_then(right, retries), view)

    assert (retries, found.summary) == ([], summary)


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


async def test_the_model_reads_the_kept_findings_the_counts_and_the_fact_ids() -> None:
    seen: list[str] = []

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        seen.extend(user_texts(messages))
        return ModelResponse(parts=[terminal_call(_RIGHT)])

    reviews = [_stored(1), _stored(2), _stored(3, "no_error"), _stored(4, "undecided")]
    await _synthesized(reviews, FunctionModel(answer))

    (prompt,) = seen
    assert '"keptFindings":[{"findingId":1,' in prompt
    assert '"impact":0.9}' in prompt
    assert (
        '"counts":{"kept":2,"rejected":1,"undecided":1,"keptGenomes":1,"genomes":0,'
        '"agreement":{"sampled":0,"agreed":0,"share":null}}'
    ) in prompt
    assert f'"runFact":"{_RUN_FACT}","countsFact":"{_COUNTS}"' in prompt
    assert '"run":{"run":{"id":' in prompt


async def test_no_kept_finding_makes_no_model_call() -> None:
    def refuse(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise AssertionError((messages, info))

    reviews = [_stored(3, "no_error", second="undecided"), _stored(4, "undecided")]
    usage = RunUsage()

    found = await synthesize(
        _view(), reviews, impacts=_IMPACTS, model=FunctionModel(refuse), usage=usage
    )

    assert found == StoredSynthesis(
        sections=(),
        headline=(),
        summary=NO_FINDING_KEPT,
        agreement=ReviewAgreement(sampled=1, agreed=0),
    )
    assert NO_FINDING_KEPT == "The review kept no finding of this run as an error."
    assert usage.requests == 0


async def test_a_synthesis_whose_retries_are_spent_stops_with_its_usage() -> None:
    def always_wrong(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        return ModelResponse(parts=[terminal_call(_draft([_section(_SPLIT, 1)], [1]))])

    usage = RunUsage()
    with pytest.raises(SynthesisStoppedError):
        await synthesize(
            _view(),
            [_stored(1)],
            impacts=_IMPACTS,
            model=FunctionModel(always_wrong),
            usage=usage,
        )

    assert usage.requests == 4


async def test_the_mock_synthesis_groups_the_kept_findings_by_impact() -> None:
    reviews = [
        _stored(2),
        _stored(4, error_type=_SPLIT),
        _stored(1, impact=0.1),
        _stored(3),
        _stored(6, "no_error"),
    ]

    found = await _synthesized(reviews, build_synthesis_mock())

    assert found == StoredSynthesis(
        sections=(
            ErrorTypeSection(
                error_type=_TRUNCATED,
                cause="The relatives of EXA_0003 are longer.",
                confirmed_by="The stored evidence of the kept findings confirms it.",
                finding_ids=(3, 2, 1),
            ),
            ErrorTypeSection(
                error_type=_SPLIT,
                cause="The relatives of EXA_0004 are longer.",
                confirmed_by="The stored evidence of the kept findings confirms it.",
                finding_ids=(4,),
            ),
        ),
        headline=(3, 2, 4, 1),
        summary=(
            f"The review kept [stat:{_COUNTS}.kept] findings as errors and "
            f"rejected [stat:{_COUNTS}.rejected]."
        ),
        agreement=ReviewAgreement(sampled=0, agreed=0),
        facts=(
            StatisticFact(
                id=_COUNTS,
                kind="audit_synthesis",
                title=f"The reviews of audit run {_RUN}",
                rows=[
                    StatisticRowFact(name="kept", value="4"),
                    StatisticRowFact(name="rejected", value="1"),
                ],
            ),
        ),
    )
