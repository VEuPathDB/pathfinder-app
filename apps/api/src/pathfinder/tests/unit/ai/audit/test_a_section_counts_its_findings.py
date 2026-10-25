from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from assistant_core.models.scripted import retry_prompt_parts, terminal_call
from pydantic_ai.messages import ModelMessage, ModelResponse, RetryPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RunUsage

from pathfinder.ai.audit.instructions import SYNTHESIS_INSTRUCTIONS
from pathfinder.ai.audit.synthesis import synthesize
from pathfinder.domain.audit.rates import TargetReport
from pathfinder.domain.audit.run_state import LeftUnits
from pathfinder.domain.audit.scope import AuditScope
from pathfinder.domain.audit.stages import RunStages
from pathfinder.domain.audit.verdicts import (
    ErrorTypeSection,
    FindingReview,
    GeneModelVerdict,
    finding_cite,
)
from pathfinder.domain.reference_placement import written_numbers
from pathfinder.services.audit.verdicts import VerdictView
from pathfinder.services.audit.views import AuditRunSummary, AuditRunView

_NOW = datetime(2026, 10, 25, tzinfo=UTC)
_RUN = UUID("00000000-0000-4000-8000-000000000003")
_NF54 = "Plasmodium falciparum NF54"
_INTACT = [9, 11, 14, 19, 21, 27]
_RECORDED_CAUSE = (
    "Seven pseudogene calls are erroneous because the NF54 sequence reconstructs "
    "the complete reference coding sequence with full coverage, no premature "
    "stops, and no amino-acid differences; stored pseudogenic-transcript evidence "
    "does not outweigh the direct sequence confirmation."
)
_TRUNCATED_CAUSE = (
    "The NF54 model is truncated: its 556-residue product is far shorter than "
    "the approximately 1,590-residue orthologs."
)
_CITES = "finding:9; evidence:9:confirmation; evidence:9:gene_evidence."


def _view() -> AuditRunView:
    return AuditRunView(
        run=AuditRunSummary(
            id=_RUN,
            site_id="plasmodb",
            conversation_id=None,
            release=None,
            status="finished",
            phase="finished",
            deadline_at=None,
            genomes=[_NF54],
            checks=["pseudogene_call"],
            targets=0,
            created_at=_NOW,
            finished_at=_NOW,
        ),
        scope=AuditScope(
            site_id="plasmodb",
            genomes=(_NF54,),
            comparison=("Plasmodium falciparum 3D7",),
            checks=("pseudogene_call",),
            reference_genome="Plasmodium falciparum 3D7",
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
        disputed=[],
    )


def _kept(finding_id: int) -> VerdictView:
    judged = GeneModelVerdict(
        genes=(f"PfNF54_{finding_id:06d}:pseudogene",),
        model_genome=_NF54,
        verdict="error",
        error_type="intact_gene_called_pseudogene",
        certainty="high",
        cause="The genome encodes the whole reference coding sequence.",
        cites=(finding_cite(finding_id),),
    )
    review = FindingReview(
        verdict=judged,
        already_known="not_searched",
        card_text="An intact gene.",
        impact=0.25,
        impact_reason="The model hides an intact gene.",
    )
    return VerdictView(
        id=finding_id,
        run_id=_RUN,
        finding_id=finding_id,
        origin="review",
        verdict=judged,
        review=review,
        created_at=_NOW,
    )


def _draft(
    cause: str, confirmed_by: str = "The sequence confirmations show it."
) -> dict[str, Any]:
    section = {
        "errorType": "intact_gene_called_pseudogene",
        "cause": cause,
        "confirmedBy": confirmed_by,
        "findingIds": _INTACT,
    }
    return {"sections": [section], "headline": _INTACT, "summary": "Intact genes."}


def _first_then(wrong: dict[str, Any], retries: list[RetryPromptPart]) -> FunctionModel:
    right = _draft("The genome encodes the whole reference coding sequence.")

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        retries.extend(retry_prompt_parts(messages))
        return ModelResponse(parts=[terminal_call(right if retries else wrong)])

    return FunctionModel(answer)


async def _synthesized(model: FunctionModel) -> list[ErrorTypeSection]:
    found = await synthesize(
        _view(),
        [_kept(f) for f in _INTACT],
        impacts=dict.fromkeys(_INTACT, 0.25),
        model=model,
        usage=RunUsage(),
    )
    return list(found.sections)


def test_a_section_counts_the_findings_it_lists() -> None:
    section = ErrorTypeSection.model_validate(_draft(_RECORDED_CAUSE)["sections"][0])

    dumped = section.model_dump(by_alias=True, mode="json")

    assert (section.count, dumped["count"], dumped["findingIds"]) == (6, 6, _INTACT)


def test_the_numbers_a_sentence_writes_are_its_words_and_its_lone_figures() -> None:
    assert written_numbers(_RECORDED_CAUSE) == ["Seven"]
    assert written_numbers("The review kept 7 of 9 findings, 88.9% of them.") == [
        "7",
        "9",
        "88.9",
    ]
    assert written_numbers(f"{_TRUNCATED_CAUSE} {_CITES} PF3D7_1423800 3D7") == []


async def test_a_section_cause_that_states_a_count_is_retried() -> None:
    retries: list[RetryPromptPart] = []

    sections = await _synthesized(_first_then(_draft(_RECORDED_CAUSE), retries))

    (retry,) = retries
    assert retry.content == (
        "The section intact_gene_called_pseudogene writes Seven in its cause or in "
        "what confirms it. A section's count is the findings its findingIds list, "
        "which the run shows beside it, so neither sentence writes a number."
    )
    assert [(s.count, s.finding_ids) for s in sections] == [(6, tuple(_INTACT))]


async def test_a_section_that_cites_and_measures_is_kept_as_written() -> None:
    retries: list[RetryPromptPart] = []
    written = _draft(_TRUNCATED_CAUSE, _CITES)

    sections = await _synthesized(_first_then(written, retries))

    assert (retries, sections[0].cause, sections[0].confirmed_by) == (
        [],
        _TRUNCATED_CAUSE,
        _CITES,
    )


def test_the_synthesizer_is_told_a_section_writes_no_number() -> None:
    told = [
        line
        for line in SYNTHESIS_INSTRUCTIONS.splitlines()
        if line.startswith("- A section's cause")
    ]

    assert told == [
        (
            "- A section's cause and what confirms it write no number: the "
            "section's count is the findings it lists, and the run shows that "
            "count beside it."
        )
    ]
