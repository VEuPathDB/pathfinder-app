from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.domain.audit.verdicts import (
    ErrorTypeSection,
    FindingReview,
    GeneModelVerdict,
    ReviewAgreement,
    SynthesisDraft,
    VerdictKind,
    evidence_cite,
    finding_cite,
    read_cite,
    review_agreement,
)

GENOME_A = "Examplea alpha A"
CALL_READ = read_cite("audit_pseudogene_call", "EXA_0001", "EXR_0001")


def _verdict(verdict: VerdictKind = "error", **overrides: object) -> GeneModelVerdict:
    fields: dict[str, object] = {
        "genes": ("EXA_0001", "EXR_0001"),
        "model_genome": GENOME_A,
        "verdict": verdict,
        "error_type": "intact_gene_called_pseudogene",
        "certainty": "high",
        "cause": "the strain gene keeps the reference reading frame",
        "cites": (CALL_READ,),
    }
    fields.update(overrides)
    return GeneModelVerdict.model_validate(fields)


def _review(
    first: VerdictKind = "error",
    second: VerdictKind | None = None,
    **overrides: object,
) -> FindingReview:
    verdict = (
        _verdict(first)
        if first == "error"
        else _verdict(first, error_type=None, certainty=None)
    )
    fields: dict[str, object] = {
        "verdict": verdict,
        "already_known": "not_searched",
        "card_text": "The strain gene is intact.",
        "second_verdict": second,
    }
    fields.update(overrides)
    return FindingReview.model_validate(fields)


def test_cites_name_their_source() -> None:
    assert (finding_cite(7), evidence_cite(7, "relatives"), CALL_READ) == (
        "finding:7",
        "evidence:7:relatives",
        "audit_pseudogene_call:EXA_0001:EXR_0001",
    )


def test_an_error_verdict_names_its_error_and_certainty() -> None:
    with pytest.raises(ValidationError, match="an error verdict names its error type"):
        _verdict(error_type=None, certainty=None)
    with pytest.raises(ValidationError, match="an error verdict names its error type"):
        _verdict("no_error")
    with pytest.raises(ValidationError, match="named together"):
        _verdict(certainty=None)
    verdict = _verdict()
    assert (verdict.error_type, verdict.certainty) == (
        "intact_gene_called_pseudogene",
        "high",
    )
    assert verdict.unheld_cites(frozenset()) == [CALL_READ]
    assert verdict.unheld_cites(frozenset({CALL_READ})) == []


def test_a_verdict_cites_at_least_one_read() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        _verdict(cites=())


def test_a_known_finding_names_its_source() -> None:
    with pytest.raises(ValidationError, match="names where it is known from"):
        _review(already_known="known")
    with pytest.raises(ValidationError, match="names where it is known from"):
        _review(already_known="not_found", known_from=("https://example.org/a",))
    known = _review(already_known="known", known_from=("https://example.org/a",))
    assert known.known_from == ("https://example.org/a",)


def test_a_changed_impact_states_why() -> None:
    with pytest.raises(ValidationError, match="a changed impact states why"):
        _review(impact=0.4)
    with pytest.raises(ValidationError, match="a changed impact states why"):
        _review(impact_reason="the gene has no ortholog")
    review = _review(impact=0.4, impact_reason="the gene has no ortholog")
    assert (review.impact, review.impact_reason) == (0.4, "the gene has no ortholog")


def test_agreement_is_a_count_and_a_share() -> None:
    reviews = [
        _review("error", "error"),
        _review("no_error", "no_error"),
        _review("error", "undecided"),
        _review("error"),
    ]
    agreement = review_agreement(reviews)
    assert agreement == ReviewAgreement(sampled=3, agreed=2)
    assert agreement.share == 0.667
    assert agreement.model_dump(by_alias=True)["share"] == 0.667
    assert review_agreement([_review("error")]).share is None
    with pytest.raises(ValidationError, match="agreement counts at most the sampled"):
        ReviewAgreement(sampled=1, agreed=2)


def test_a_stopped_review_judges_nothing_and_is_never_a_sampled_pair() -> None:
    stopped = _review("undecided", stopped=True)

    assert review_agreement([stopped, _review("error", "error")]) == ReviewAgreement(
        sampled=1, agreed=1
    )
    with pytest.raises(ValidationError, match="a stopped review judges nothing"):
        _review("undecided", "error", stopped=True)
    with pytest.raises(ValidationError, match="a stopped review judges nothing"):
        _review("error", stopped=True)


def _section(error_type: str, *finding_ids: int) -> ErrorTypeSection:
    return ErrorTypeSection.model_validate(
        {
            "error_type": error_type,
            "cause": "the strain assembly breaks the reading frame",
            "confirmed_by": "the reference protein aligns across the stop",
            "finding_ids": finding_ids,
        }
    )


def test_a_headline_is_drawn_from_the_sections() -> None:
    with pytest.raises(ValidationError, match=r"headline findings \[7\] are in no"):
        SynthesisDraft(
            sections=(_section("truncated_model", 3),),
            headline=(3, 7),
            summary="One truncated model.",
        )
    with pytest.raises(ValidationError, match="one section per error type"):
        SynthesisDraft(
            sections=(_section("truncated_model", 3), _section("truncated_model", 4)),
            headline=(),
            summary="Two sections.",
        )
    draft = SynthesisDraft(
        sections=(_section("truncated_model", 3), _section("split_model", 4)),
        headline=(4, 3),
        summary="One truncated and one split model.",
    )
    assert draft.headline == (4, 3)
