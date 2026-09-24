"""The evidence behind one verification: what each control test filed, the
count of each step on the site, and the references each criterion was bound on.

Every value is read from a tool result, the ledger or the site. None is model text.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Literal, Self

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field, model_validator

# Whether the site's counts were read: read, asked and not answered, or not
# asked because the strategy is not on the site.
type SiteRead = Literal["read", "not_answered", "not_read"]


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

    ``refused_because`` is the ledger's own sentence for a refused success.
    """

    model_config = ConfigDict(frozen=True)

    supported: bool
    pending_checks: list[str] = Field(default_factory=list)
    refused_because: str | None = None


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
        ]


__all__ = [
    "CheckedStepCount",
    "ControlEnrichment",
    "ControlSetEvidence",
    "ControlTestEvidence",
    "CriterionCitations",
    "EvidenceCard",
    "EvidenceVerdict",
    "SiteRead",
]
