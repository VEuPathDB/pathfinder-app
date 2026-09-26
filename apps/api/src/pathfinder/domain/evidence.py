"""The evidence behind one verification: the control results, the step counts,
the references of each criterion, and the review VERIFY wrote."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Literal, Self

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field, model_validator

# Whether the site's counts were read: read, asked and not answered, or not
# asked because the strategy is not on the site.
type SiteRead = Literal["read", "not_answered", "not_read"]

# The most genes one check samples and reads the record of.
SAMPLED_GENE_LIMIT = 8

type RequirementHow = Literal[
    "search", "parameter", "structure", "transform", "analysis"
]
type RequirementStatus = Literal["met", "unmet", "unexpressed"]
type GeneFit = Literal["yes", "no", "unclear"]
type CitationKind = Literal["record", "literature", "web"]


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


class ControlEnrichment(CamelModel):
    """The one-sided hypergeometric test of positives among the returned controls.

    The population is every control tested, the draws are the controls the
    target returned, and ``p_value`` is the chance of at least that many positives.
    """

    model_config = ConfigDict(frozen=True)

    population: int = Field(ge=1)
    positives: int = Field(ge=0)
    returned: int = Field(ge=0)
    positives_returned: int = Field(ge=0)
    p_value: float = Field(ge=0.0, le=1.0)


class ControlTestEvidence(CamelModel):
    """One control test: the target it read and the sets it was given."""

    model_config = ConfigDict(frozen=True)

    tested_label: str
    # The step the test read; None for a test that ran a search on its own.
    wdk_step_id: int | None = None
    positive: ControlSetEvidence | None = None
    negative: ControlSetEvidence | None = None
    enrichment: ControlEnrichment | None = None

    @model_validator(mode="after")
    def _the_sets_back_the_enrichment(self) -> Self:
        if self.positive is None and self.negative is None:
            msg = "a control test holds at least one control set"
            raise ValueError(msg)
        enrichment = self.enrichment
        if enrichment is None:
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


class EvidenceVerdict(CamelModel):
    """The verdict as the ledger holds it after the build check.

    ``refused_because`` is the ledger's own sentence for a verdict it does not
    support, whichever side found the failure.
    """

    model_config = ConfigDict(frozen=True)

    supported: bool
    pending_checks: list[str] = Field(default_factory=list)
    refused_because: str | None = None


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
            "met: the strategy states it. unmet: the strategy can state it and "
            "does not. unexpressed: no search the site offers can state it."
        )
    )
    note: str = Field(
        default="",
        max_length=300,
        description="One line: the parameter value or the combine, or why nothing.",
    )

    @model_validator(mode="after")
    def _a_met_requirement_names_its_answer(self) -> Self:
        if self.status == "met" and not self.answered_by:
            msg = "a met requirement names the criterion or the step that answers it"
            raise ValueError(msg)
        return self


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
        description="One line naming the evidence read: a sampled value, the "
        "product, a GO term, an expression value.",
    )


class SourceReference(CamelModel):
    """One source an answer names, by the identifiers a reader opens it with."""

    model_config = ConfigDict(frozen=True)

    kind: CitationKind
    label: str = Field(
        min_length=1,
        max_length=200,
        description=(
            "What the reader sees: the gene id and the site for a record, the "
            "title for a paper or a page."
        ),
    )
    url: str | None = None
    doi: str | None = None
    pmid: str | None = None

    @model_validator(mode="after")
    def _a_source_can_be_opened(self) -> Self:
        if not self.references():
            msg = "a source carries a url, a DOI or a PMID"
            raise ValueError(msg)
        return self

    def references(self) -> list[str]:
        """Every identifier this source is checked by."""
        return [value for value in (self.url, self.doi, self.pmid) if value]


class Citation(SourceReference):
    """One source the check retrieved, and what it settles."""

    why: str = Field(min_length=1, max_length=300)


class VerificationReview(CamelModel):
    """What the check read against the researcher's words: each stated
    requirement, a sample of the genes, and the sources it retrieved."""

    model_config = ConfigDict(frozen=True)

    requirements: list[RequirementCheck] = Field(
        default_factory=list,
        max_length=20,
        description="One row per requirement the researcher stated, in any message.",
    )
    sampled_genes: list[SampledGene] = Field(
        default_factory=list,
        max_length=SAMPLED_GENE_LIMIT,
        description="The root step's genes whose record this check read.",
    )
    sources: list[Citation] = Field(
        default_factory=list,
        max_length=10,
        description="Each paper or page a research read of this turn returned.",
    )

    def unmet(self) -> list[RequirementCheck]:
        """The requirements the strategy can state and does not."""
        return [row for row in self.requirements if row.status == "unmet"]

    def to_report(self) -> list[RequirementCheck]:
        """The requirements a reply must name: the unmet and the unexpressed."""
        return [row for row in self.requirements if row.status != "met"]

    def misfit_caveat(self) -> str | None:
        """One line counting the sampled genes that do not fit, or None."""
        misfits = [gene for gene in self.sampled_genes if gene.fits == "no"]
        if not misfits:
            return None
        listed = "; ".join(f"`{gene.gene_id}` ({gene.why})" for gene in misfits)
        return (
            f"{len(misfits)} of {len(self.sampled_genes)} sampled genes do not "
            f"fit: {listed}"
        )

    def texts(self) -> list[str]:
        """Every text of the review that is not a gene id or a step id."""
        return [
            *(t for row in self.requirements for t in (row.text, row.note) if t),
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
    verdict: EvidenceVerdict
    review: VerificationReview = Field(default_factory=VerificationReview)

    def texts(self) -> list[str]:
        """Every text on the card that is not a count, a gene id or a WDK id."""
        return [
            *([] if self.strategy_url is None else [self.strategy_url]),
            *(
                []
                if self.verdict.refused_because is None
                else [self.verdict.refused_because]
            ),
            *self.verdict.pending_checks,
            *(step.title for step in self.steps),
            *(test.tested_label for test in self.controls),
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
    "Citation",
    "CitationKind",
    "ControlEnrichment",
    "ControlSetEvidence",
    "ControlTestEvidence",
    "CriterionCitations",
    "EvidenceCard",
    "EvidenceVerdict",
    "GeneFit",
    "RequirementCheck",
    "RequirementHow",
    "RequirementStatus",
    "SampledGene",
    "SiteRead",
    "SourceReference",
    "VerificationReview",
]
