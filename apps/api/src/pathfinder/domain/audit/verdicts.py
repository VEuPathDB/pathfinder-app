"""What a model judged about a gene model, what a review adds to it, and the synthesis of a run."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Self

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field, model_validator

from pathfinder.domain.audit.findings import Certainty, ErrorType
from pathfinder.domain.audit.scope import GeneName, OrganismName
from pathfinder.domain.statistic_facts import Share

VerdictKind = Literal["error", "no_error", "undecided"]
VerdictOrigin = Literal["auditor", "lead", "verification", "review"]
LiteratureStatus = Literal["known", "not_found", "not_searched"]
ReviewStatus = Literal["waiting", "reviewing", "synthesized", "stopped"]
MAX_CAUSE = 600
MAX_CARD = 1200
MAX_CITES = 12
MAX_REVIEWS_PER_RUN = 50
MAX_HEADLINES = 10
AGREEMENT_SAMPLE = 10


def finding_cite(finding_id: int) -> str:
    return f"finding:{finding_id}"


def evidence_cite(finding_id: int, kind: str) -> str:
    return f"evidence:{finding_id}:{kind}"


def read_cite(tool_name: str, *subjects: str) -> str:
    return ":".join([tool_name, *subjects])


class GeneModelVerdict(CamelModel):
    model_config = ConfigDict(frozen=True)

    genes: tuple[GeneName, ...] = Field(min_length=1, max_length=4)
    model_genome: OrganismName
    verdict: VerdictKind
    error_type: ErrorType | None = None
    certainty: Certainty | None = None
    cause: str = Field(min_length=1, max_length=MAX_CAUSE)
    cites: tuple[str, ...] = Field(min_length=1, max_length=MAX_CITES)

    @model_validator(mode="after")
    def _named_when_an_error(self) -> Self:
        if (self.verdict == "error") != (self.error_type is not None):
            msg = (
                "an error verdict names its error type, and only an error verdict does"
            )
            raise ValueError(msg)
        if (self.error_type is None) != (self.certainty is None):
            msg = "an error type and its certainty are named together"
            raise ValueError(msg)
        return self

    def unheld_cites(self, held: frozenset[str]) -> list[str]:
        return [cite for cite in self.cites if cite not in held]


class FindingReview(CamelModel):
    model_config = ConfigDict(frozen=True)

    verdict: GeneModelVerdict
    already_known: LiteratureStatus
    known_from: tuple[str, ...] = Field(default=(), max_length=MAX_CITES)
    paper_depends: bool | None = None
    card_text: str = Field(min_length=1, max_length=MAX_CARD)
    impact: float | None = Field(default=None, ge=0.0, le=1.0)
    impact_reason: str | None = Field(default=None, max_length=MAX_CAUSE)
    second_verdict: VerdictKind | None = None
    stopped: bool = False

    @model_validator(mode="after")
    def _sourced(self) -> Self:
        if self.stopped and (self.verdict.verdict, self.second_verdict) != (
            "undecided",
            None,
        ):
            msg = "a stopped review judges nothing and holds no second verdict"
            raise ValueError(msg)
        if (self.already_known == "known") != bool(self.known_from):
            msg = "a finding already known names where it is known from, and only then"
            raise ValueError(msg)
        if (self.impact is None) != (self.impact_reason is None):
            msg = "a changed impact states why"
            raise ValueError(msg)
        return self


class ErrorTypeSection(CamelModel):
    model_config = ConfigDict(frozen=True)

    error_type: ErrorType
    cause: str = Field(min_length=1, max_length=MAX_CAUSE)
    confirmed_by: str = Field(min_length=1, max_length=MAX_CAUSE)
    finding_ids: tuple[int, ...] = Field(min_length=1)


class ReviewAgreement(CamelModel):
    model_config = ConfigDict(frozen=True)

    sampled: int = Field(ge=0)
    agreed: int = Field(ge=0)

    @model_validator(mode="after")
    def _agreed_within_sampled(self) -> Self:
        if self.agreed > self.sampled:
            msg = "agreement counts at most the sampled reviews"
            raise ValueError(msg)
        return self

    @computed
    def share(self) -> Share | None:
        return None if self.sampled == 0 else round(self.agreed / self.sampled, 3)


def review_agreement(reviews: Sequence[FindingReview]) -> ReviewAgreement:
    paired = [r for r in reviews if r.second_verdict is not None]
    return ReviewAgreement(
        sampled=len(paired),
        agreed=sum(r.verdict.verdict == r.second_verdict for r in paired),
    )


class SynthesisDraft(CamelModel):
    model_config = ConfigDict(frozen=True)

    sections: tuple[ErrorTypeSection, ...]
    headline: tuple[int, ...] = Field(max_length=MAX_HEADLINES)
    summary: str = Field(min_length=1, max_length=MAX_CARD)

    @model_validator(mode="after")
    def _headline_in_sections(self) -> Self:
        types = [section.error_type for section in self.sections]
        if len(types) != len(set(types)):
            msg = "a synthesis holds one section per error type"
            raise ValueError(msg)
        named = {f for section in self.sections for f in section.finding_ids}
        outside = [f for f in self.headline if f not in named]
        if outside:
            msg = f"headline findings {outside} are in no section"
            raise ValueError(msg)
        return self


class Synthesis(SynthesisDraft):
    agreement: ReviewAgreement


class ReviewProgress(CamelModel):
    model_config = ConfigDict(frozen=True)

    status: ReviewStatus
    done: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)
    message: str = ""
