"""The evidence behind one verification: the control results, the step counts,
the references of each criterion, and the checks the site's answers decide."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal, Self

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field, model_validator

from pathfinder.domain.citations import Citation
from pathfinder.domain.clipped import list_clipped_to, text_clipped_to
from pathfinder.domain.column_fit import ColumnFit
from pathfinder.domain.control_enrichment import ControlEnrichment
from pathfinder.domain.expression_fit import ExpressionFit
from pathfinder.domain.omitted_from_input import OmittedFromInput
from pathfinder.domain.site_checks import SiteCheck

# Whether the site's counts were read: read, asked and not answered, or not
# asked because the strategy is not on the site.
type SiteRead = Literal["read", "not_answered", "not_read"]

# The most genes one check samples and reads the record of.
SAMPLED_GENE_LIMIT = 8

type GeneFit = Literal["yes", "no", "unclear"]


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


class SampledGene(CamelModel):
    """One gene of the result, read from its record and judged against the request."""

    model_config = ConfigDict(frozen=True)

    gene_id: str = Field(min_length=1)
    product: str = ""
    organism: str = ""
    fits: GeneFit
    why: Annotated[str, text_clipped_to(300)] = Field(
        min_length=1,
        description="The evidence read; when the fit is no, what the record lacks.",
    )


WithheldKind = Literal["sampled_gene", "source"]
StoredWithheldKind = WithheldKind | Literal["claim"]


class WithheldEvidence(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: StoredWithheldKind
    sentence: str


class VerificationReview(CamelModel):
    """What the check read: each check the site's answers decide, the columns
    of each step, a sample of the genes where no column shows a value, and the
    sources it retrieved."""

    model_config = ConfigDict(frozen=True)

    checks: Annotated[list[SiteCheck], OmittedFromInput] = Field(default_factory=list)
    column_fits: Annotated[list[ColumnFit], OmittedFromInput] = Field(
        default_factory=list
    )
    sampled_genes: Annotated[list[SampledGene], list_clipped_to(SAMPLED_GENE_LIMIT)] = (
        Field(
            default_factory=list,
            description=(
                "The root step's genes whose record this check read, for a "
                "criterion no column shows."
            ),
        )
    )
    sources: Annotated[list[Citation], list_clipped_to(10)] = Field(
        default_factory=list,
        description="Each paper or page a research read of this turn returned.",
    )
    withheld: Annotated[list[WithheldEvidence], OmittedFromInput] = Field(
        default_factory=list
    )

    def texts(self) -> list[str]:
        """Every text of the review that is not a gene id or a step id."""
        return [
            *(t for check in self.checks for t in check.texts()),
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
    expression_fits: list[ExpressionFit] = Field(default_factory=list)

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
    "ControlSetEvidence",
    "ControlTestEvidence",
    "CriterionCitations",
    "EvidenceCard",
    "GeneFit",
    "NamedControlSet",
    "SampledGene",
    "SiteRead",
    "VerificationReview",
]
