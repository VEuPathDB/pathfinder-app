"""The evidence behind one verification: the control results, the step counts,
the references of each criterion, and the review VERIFY wrote."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from typing import Literal, Self

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from pathfinder.domain.citations import Citation
from pathfinder.domain.control_enrichment import ControlEnrichment

# Whether the site's counts were read: read, asked and not answered, or not
# asked because the strategy is not on the site.
type SiteRead = Literal["read", "not_answered", "not_read"]

# The most genes one check samples and reads the record of.
SAMPLED_GENE_LIMIT = 8

type RequirementHow = Literal[
    "search", "parameter", "structure", "transform", "analysis"
]
type RequirementStatus = Literal["met", "unmet", "unexpressed"]
# unshown: a record the check read shows a met row missing.
# unjudged: no record the check read judged a met row either way.
type ShownStatus = RequirementStatus | Literal["unshown", "unjudged"]
type GeneFit = Literal["yes", "no", "unclear"]
type ColumnFitState = Literal["all", "some", "none", "not_shown"]
# A column reporter counts the step's genes; an attribute histogram counts its
# transcript rows.
type CountedIn = Literal["genes", "transcripts"]


class ControlSetEvidence(CamelModel):
    """One control set of a test: the controls the target returned and the rest.

    The two lists partition the controls, so every count is read from them.
    """

    model_config = ConfigDict(frozen=True)

    returned: list[str]
    not_returned: list[str]

    @model_validator(mode="after")
    def _the_lists_partition_the_controls(self) -> Self:
        filed = Counter([*self.returned, *self.not_returned])
        if not filed:
            msg = "a control set holds at least one id"
            raise ValueError(msg)
        repeated = sorted(gene_id for gene_id, times in filed.items() if times > 1)
        if repeated:
            msg = f"a control id is filed on one list only: {repeated}"
            raise ValueError(msg)
        return self

    @computed
    def controls_count(self) -> int:
        """Every control of this set."""
        return len(self.returned) + len(self.not_returned)

    @computed
    def returned_count(self) -> int:
        """The controls the target returned."""
        return len(self.returned)

    @computed
    def rate(self) -> float:
        """The share of the controls the target returned."""
        return self.returned_count / self.controls_count


class NamedControlSet(CamelModel):
    """The saved control set a control test ran."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str

    def redacted(self, redact: Callable[[str], str]) -> NamedControlSet:
        return self.model_copy(update={"name": redact(self.name)})


class ControlTestEvidence(CamelModel):
    """One control test: the target it read and the sets it was given."""

    model_config = ConfigDict(frozen=True)

    tested_label: str
    # The step the test read; None for a test that ran a search on its own.
    wdk_step_id: int | None = None
    # The saved set the test ran; None when its ids were not a saved set.
    control_set: NamedControlSet | None = None
    positive: ControlSetEvidence | None = None
    negative: ControlSetEvidence | None = None
    enrichment: ControlEnrichment | None = None

    @model_validator(mode="after")
    def _the_sets_back_the_enrichment(self) -> Self:
        if self.positive is None and self.negative is None:
            msg = "a control test holds at least one control set"
            raise ValueError(msg)
        if (enrichment := self.enrichment) is None:
            return self
        if self.positive is None or self.negative is None:
            msg = "an enrichment row needs both a positive and a negative set"
            raise ValueError(msg)
        expected = (
            self.positive.controls_count + self.negative.controls_count,
            self.positive.controls_count,
            self.positive.returned_count + self.negative.returned_count,
            self.positive.returned_count,
        )
        stated = (
            enrichment.population,
            enrichment.positives,
            enrichment.returned,
            enrichment.positives_returned,
        )
        if stated != expected:
            msg = f"the enrichment counts {stated} are not the sets' {expected}"
            raise ValueError(msg)
        return self


class CheckedStepCount(CamelModel):
    """One step of the judged strategy: the count the build recorded and the site's."""

    model_config = ConfigDict(frozen=True)

    step_id: str
    wdk_step_id: int
    title: str
    recorded_count: int | None = None
    # None when the site did not answer at the check.
    site_count: int | None = None

    @computed
    def drifted(self) -> bool:
        """The site counts the step differently from the build."""
        return (
            self.recorded_count is not None
            and self.site_count is not None
            and self.recorded_count != self.site_count
        )


class CriterionCitations(CamelModel):
    """The references a criterion was bound on, each one a read of the turn returned."""

    model_config = ConfigDict(frozen=True)

    criterion_id: str
    criterion_text: str
    references: list[str] = Field(min_length=1)


class RequirementCheck(CamelModel):
    """One requirement the researcher stated, and what in the strategy answers it."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(
        min_length=1,
        max_length=300,
        description="The requirement in the researcher's own words.",
    )
    turn: int = Field(
        ge=1,
        description="The number of the researcher's message that stated it.",
    )
    answered_by: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="The criterion ids or step ids that answer it.",
    )
    how: RequirementHow = Field(
        description=(
            "search: a search states it. parameter: a parameter value states it. "
            "structure: a combine states it. transform: a transform step states "
            "it. analysis: a study analysis states it."
        )
    )
    status: RequirementStatus = Field(
        description=(
            "met: a step states it. unmet: the strategy can state it and no "
            "step does; answered_by is then empty. unexpressed: no search the "
            "site offers can state it."
        )
    )
    note: str = Field(
        default="",
        max_length=300,
        description="One line: the parameter value or the combine, or why nothing.",
    )
    shown_by: list[str] = Field(
        default_factory=list,
        max_length=SAMPLED_GENE_LIMIT,
        description="The sampled gene ids or the columns whose fit show it.",
    )
    # The runtime's marks, hidden from the check: a text query alone answers
    # the met row, and a record the check read shows it missing, or no record
    # judged it either way.
    no_record_shows_it: SkipJsonSchema[bool] = False
    no_record_judged_it: SkipJsonSchema[bool] = False

    @model_validator(mode="after")
    def _a_status_agrees_with_its_answer(self) -> Self:
        if self.status == "met" and not self.answered_by:
            msg = "a met requirement names the criterion or the step that answers it"
            raise ValueError(msg)
        if self.status == "unmet" and self.answered_by:
            msg = (
                "an unmet requirement names no step that answers it: a step "
                "that states it makes the row met, and a step that states "
                "another value or joins the steps another way is named in the note"
            )
            raise ValueError(msg)
        if (self.no_record_shows_it or self.no_record_judged_it) and (
            self.status != "met" or self.no_record_shows_it == self.no_record_judged_it
        ):
            msg = "a met row the records leave short is either unshown or unjudged"
            raise ValueError(msg)
        return self

    @property
    def shown_status(self) -> ShownStatus:
        """The status a reader is shown: a met row the records show missing is
        unshown, and one no record judged is unjudged."""
        if self.no_record_shows_it:
            return "unshown"
        return "unjudged" if self.no_record_judged_it else self.status


class SampledGene(CamelModel):
    """One gene of the result, read from its record and judged against the request."""

    model_config = ConfigDict(frozen=True)

    gene_id: str = Field(min_length=1)
    product: str = ""
    organism: str = ""
    fits: GeneFit
    why: str = Field(
        min_length=1,
        max_length=300,
        description="The evidence read; when the fit is no, what the record lacks.",
    )


def _counted(surely: int, at_most: int) -> str:
    return str(surely) if surely == at_most else f"{surely} to {at_most}"


# The counts a column fit row opens with: "569 of 569 transcripts fit" or
# "300 of 569 transcripts hold". A row counts records in the column's own unit.
COLUMN_FIT_COUNTS = re.compile(
    r"\b\d[\d,]*(?: to \d[\d,]*)? of \d[\d,]* (?:genes|transcripts) (?:fit|hold)\b"
)


class ThresholdSides(CamelModel):
    """The records on each side of one threshold whose direction the site does
    not state, when the step does not hold every record on one side."""

    model_config = ConfigDict(frozen=True)

    value: str
    # The records at the threshold or above it; a bin across it raises the most.
    above: int = Field(ge=0)
    above_at_most: int = Field(ge=0)
    below: int = Field(ge=0)
    below_at_most: int = Field(ge=0)

    @model_validator(mode="after")
    def _the_counts_nest(self) -> Self:
        if self.above > self.above_at_most or self.below > self.below_at_most:
            msg = "each side of a threshold holds surely <= at_most"
            raise ValueError(msg)
        return self

    def sentence(self, total: int, counted_in: CountedIn, display_name: str) -> str:
        return (
            f"{_counted(self.above, self.above_at_most)} of {total} {counted_in} "
            f"hold {display_name} {self.value} or more and "
            f"{_counted(self.below, self.below_at_most)} hold {self.value} or fewer"
        )


class ColumnFit(CamelModel):
    """One column of a step's search, read over the whole step against the
    values its criterion binds."""

    model_config = ConfigDict(frozen=True)

    criterion_id: str
    criterion_text: str
    wdk_step_id: int
    column: str
    display_name: str
    # The bounds whose side is known, as one range; empty when none is.
    bound_value: str
    counted_in: CountedIn = "genes"
    total: int = Field(ge=0)
    # The records inside ``bound_value``; a bin across a bound raises the most.
    fitting: int = Field(ge=0)
    fitting_at_most: int = Field(ge=0)
    # False when the site reports no value of the column for the step.
    shown: bool = True
    sides: list[ThresholdSides] = Field(default_factory=list)

    @model_validator(mode="after")
    def _the_counts_nest(self) -> Self:
        if not self.fitting <= self.fitting_at_most <= self.total:
            msg = "a column fit holds fitting <= fitting_at_most <= total"
            raise ValueError(msg)
        if any(
            max(side.above_at_most, side.below_at_most) > self.total
            for side in self.sides
        ):
            msg = "a side of a threshold holds at most the step's records"
            raise ValueError(msg)
        if not self.shown and (self.total or self.sides):
            msg = "a column the site does not show carries no count"
            raise ValueError(msg)
        return self

    @computed
    def fits(self) -> ColumnFitState:
        """How many records of the step hold a value inside every bound."""
        if not self.shown:
            return "not_shown"
        if self.fitting_at_most == 0:
            return "none"
        return "all" if self.fitting == self.total and not self.sides else "some"

    @computed
    def sentence(self) -> str:
        """The records that fit out of the step, the records on each side of a
        threshold with no stated direction, or that the site shows no column."""
        if not self.shown:
            return f"the site shows no column for '{self.criterion_text}'"
        inside = (
            [
                (
                    f"{_counted(self.fitting, self.fitting_at_most)} of {self.total} "
                    f"{self.counted_in} fit {self.display_name} ({self.bound_value})"
                )
            ]
            if self.bound_value
            else []
        )
        sides = [
            side.sentence(self.total, self.counted_in, self.display_name)
            for side in self.sides
        ]
        return "; ".join([*inside, *sides])

    @property
    def column_key(self) -> tuple[int, str]:
        """The step and the column this fit reads."""
        return self.wdk_step_id, self.column

    def texts(self) -> list[str]:
        return [self.criterion_text, self.display_name, self.bound_value]


class VerificationReview(CamelModel):
    """What the check read against the researcher's words: each stated
    requirement, the columns of each step, a sample of the genes where no
    column shows a value, and the sources it retrieved."""

    model_config = ConfigDict(frozen=True)

    requirements: list[RequirementCheck] = Field(
        default_factory=list,
        max_length=20,
        description="One row per requirement the researcher stated, in any message.",
    )
    column_fits: list[ColumnFit] = Field(
        default_factory=list,
        description=(
            "Filled by the runtime from this turn's read_step_columns calls; "
            "anything written here is replaced."
        ),
    )
    sampled_genes: list[SampledGene] = Field(
        default_factory=list,
        max_length=SAMPLED_GENE_LIMIT,
        description=(
            "The root step's genes whose record this check read, for a "
            "criterion no column shows."
        ),
    )
    sources: list[Citation] = Field(
        default_factory=list,
        max_length=10,
        description="Each paper or page a research read of this turn returned.",
    )

    def to_report(self) -> list[RequirementCheck]:
        """The requirements a reader is shown short of met: the unmet, the
        unexpressed and the unjudged."""
        return [row for row in self.requirements if row.shown_status != "met"]

    def texts(self) -> list[str]:
        """Every text of the review that is not a gene id or a step id."""
        return [
            *(t for row in self.requirements for t in (row.text, row.note) if t),
            *(t for fit in self.column_fits for t in fit.texts()),
            *(
                t
                for gene in self.sampled_genes
                for t in (gene.product, gene.organism, gene.why)
                if t
            ),
            *(
                t
                for cited in self.sources
                for t in (cited.label, cited.why, *cited.references())
            ),
        ]


class EvidenceCard(CamelModel):
    """The evidence behind one verification of one strategy revision."""

    model_config = ConfigDict(frozen=True)

    check_id: str
    revision: str
    site_id: str
    checked_at: datetime
    wdk_strategy_id: int | None = None
    strategy_url: str | None = None
    site_read: SiteRead
    steps: list[CheckedStepCount]
    controls: list[ControlTestEvidence]
    citations: list[CriterionCitations]
    # The study steps whose analysis the site did not describe, so no check ran.
    pending_checks: list[str] = Field(default_factory=list)
    review: VerificationReview = Field(default_factory=VerificationReview)

    def texts(self) -> list[str]:
        """Every text on the card that is not a count, a gene id or a WDK id."""
        return [
            *([] if self.strategy_url is None else [self.strategy_url]),
            *self.pending_checks,
            *(step.title for step in self.steps),
            *(test.tested_label for test in self.controls),
            *(test.control_set.name for test in self.controls if test.control_set),
            *(
                text
                for cited in self.citations
                for text in (cited.criterion_text, *cited.references)
            ),
            *self.review.texts(),
        ]


__all__ = [
    "SAMPLED_GENE_LIMIT",
    "CheckedStepCount",
    "ColumnFit",
    "ColumnFitState",
    "ControlSetEvidence",
    "ControlTestEvidence",
    "CountedIn",
    "CriterionCitations",
    "EvidenceCard",
    "GeneFit",
    "NamedControlSet",
    "RequirementCheck",
    "RequirementHow",
    "RequirementStatus",
    "SampledGene",
    "ShownStatus",
    "SiteRead",
    "ThresholdSides",
    "VerificationReview",
]
