"""What a separation run offers: a measured strategy, the counts the site returned
for it, and what each of its criteria adds.

Every count is read from a WDK step. None is model text.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Self

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field, model_validator
from veupathdb.domain.strategy import CombineOp
from veupathdb_mcp.separation import SkipReason

from pathfinder.domain.evidence import (
    ControlEnrichment,
    ControlSetEvidence,
    ControlTestEvidence,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    StructureNode,
)
from pathfinder.domain.strategy.step_rationale import ControlsInforms, ControlsSource

SeparationMode = Literal["exact", "similar"]

# A run's budget is an estimate of WDK requests: one measurement is about ten.
SEPARATION_BUDGET = 600
SEPARATION_BUDGET_MIN = 200
SEPARATION_BUDGET_MAX = 2000

_OFFERED = "the offered strategy"

# A reference in the form a read of this turn returned it, or None.
type RetrievedAs = Callable[[str], str | None]


class MeasuredCriterion(CamelModel):
    """One measured candidate as the figure shows it."""

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    search_name: str
    display_name: str
    source: ControlsSource
    basis: str
    reference: str | None = None
    result_size: int
    recovered: int
    positives: int
    admitted: int
    negatives: int
    informs: ControlsInforms


class SkippedCriterion(CamelModel):
    """A candidate the run did not measure, and why."""

    model_config = ConfigDict(frozen=True)

    search_name: str
    source: ControlsSource
    basis: str
    reason: SkipReason
    detail: str = ""


class OfferedLeaf(CamelModel):
    """One criterion of the offered tree, and the controls its own step returned."""

    model_config = ConfigDict(frozen=True)

    criterion_id: str
    display_name: str
    controls: ControlTestEvidence


class LeafContribution(CamelModel):
    """What the offered tree loses or gains without one of its criteria.

    Each list is read by dropping the criterion and evaluating the rest of the
    tree over the measured control sets.
    """

    model_config = ConfigDict(frozen=True)

    criterion_id: str
    display_name: str
    # Positives the tree no longer returns without it.
    only_recovers: list[str]
    # Positives the tree returns only without it.
    holds_back: list[str]
    # Negatives the tree returns only without it.
    only_excludes: list[str]
    # Negatives the tree no longer returns without it.
    brings_in: list[str]

    @computed
    def positive_change(self) -> int:
        """The change in returned positives when the criterion is dropped."""
        return len(self.holds_back) - len(self.only_recovers)

    @computed
    def negative_change(self) -> int:
        """The change in returned negatives when the criterion is dropped."""
        return len(self.only_excludes) - len(self.brings_in)

    @computed
    def line(self) -> str:
        """The two changes as the card's column reads them."""
        return (
            f"without it: {_signed(self.positive_change)} positives, "
            f"{_signed(self.negative_change)} negatives"
        )


def _signed(change: int) -> str:
    return f"{change:+d}" if change else "0"


@dataclass(frozen=True)
class _Returned:
    positives: frozenset[str]
    negatives: frozenset[str]


_NOTHING = _Returned(frozenset(), frozenset())


def _returned(leaf: OfferedLeaf) -> _Returned:
    positive, negative = leaf.controls.positive, leaf.controls.negative
    return _Returned(
        positives=frozenset([] if positive is None else positive.returned),
        negatives=frozenset([] if negative is None else negative.returned),
    )


def _combined(
    operator: CombineOp | None, left: _Returned, right: _Returned
) -> _Returned:
    match operator:
        case CombineOp.UNION:
            return _Returned(
                left.positives | right.positives, left.negatives | right.negatives
            )
        case CombineOp.INTERSECT:
            return _Returned(
                left.positives & right.positives, left.negatives & right.negatives
            )
        case CombineOp.MINUS:
            return _Returned(
                left.positives - right.positives, left.negatives - right.negatives
            )
        case _:
            msg = f"a separation tree combines by UNION, INTERSECT or MINUS: {operator}"
            raise ValueError(msg)


def _evaluate(
    node: StructureNode, sets: Mapping[str, _Returned], dropped: str
) -> _Returned | None:
    """The controls a tree returns without one leaf, or None when nothing is left.

    A combine that loses an input is replaced by the other, as a delete of
    that step leaves the strategy.
    """
    if node.kind == "leaf":
        return None if node.criterion_id == dropped else sets[node.criterion_id or ""]
    held = [
        found
        for child in node.inputs
        if (found := _evaluate(child, sets, dropped)) is not None
    ]
    if not held:
        return None
    total = held[0]
    for other in held[1:]:
        total = _combined(node.operator, total, other)
    return total


def ablate(
    root: StructureNode, leaves: Sequence[OfferedLeaf]
) -> list[LeafContribution]:
    """What each leaf adds to the tree, left to right, from the measured sets."""
    sets = {leaf.criterion_id: _returned(leaf) for leaf in leaves}
    whole = _evaluate(root, sets, "") or _NOTHING
    found: list[LeafContribution] = []
    for leaf in leaves:
        without = _evaluate(root, sets, leaf.criterion_id) or _NOTHING
        found.append(
            LeafContribution(
                criterion_id=leaf.criterion_id,
                display_name=leaf.display_name,
                only_recovers=sorted(whole.positives - without.positives),
                holds_back=sorted(without.positives - whole.positives),
                only_excludes=sorted(without.negatives - whole.negatives),
                brings_in=sorted(whole.negatives - without.negatives),
            )
        )
    return found


def _searches_words(count: int) -> str:
    return "1 search" if count == 1 else f"{count} searches"


def _returned_words(tested: ControlSetEvidence, kind: str) -> str:
    return f"{tested.returned_count} of {tested.controls_count} {kind}"


def _read_references(criterion: Criterion, retrieved_as: RetrievedAs) -> Criterion:
    chosen = criterion.rationale
    if chosen is None or chosen.kind != "controls":
        return criterion
    kept = [found for ref in chosen.sources if (found := retrieved_as(ref))]
    return criterion.model_copy(
        update={"rationale": chosen.model_copy(update={"sources": kept})}
    )


def _offered_read(
    positive: ControlSetEvidence,
    negative: ControlSetEvidence,
    enrichment: ControlEnrichment,
) -> ControlTestEvidence:
    """The read as one control result, which refuses an enrichment row the sets
    do not back."""
    return ControlTestEvidence(
        tested_label=_OFFERED,
        positive=positive,
        negative=negative,
        enrichment=enrichment,
    )


class SeparationOffer(CamelModel):
    """The strategy a separation run offers, and the counts the site returned for it."""

    model_config = ConfigDict(frozen=True)

    task_id: str
    site_id: str
    mode: SeparationMode
    # Every criterion is bound, so the spec builds with no model in between.
    spec: OperationalSpec
    # The site's own read of the assembled tree.
    positive: ControlSetEvidence
    negative: ControlSetEvidence
    enrichment: ControlEnrichment
    result_size: int | None
    separates: bool
    # Whether the measured sets predicted the read the site returned.
    predicted_matches_read: bool
    leaves: list[OfferedLeaf]

    @model_validator(mode="after")
    def _the_sets_back_the_enrichment(self) -> Self:
        _offered_read(self.positive, self.negative, self.enrichment)
        return self

    @property
    def read(self) -> ControlTestEvidence:
        """The site's read of the offered tree, as one control result."""
        return _offered_read(self.positive, self.negative, self.enrichment)

    @computed
    def contributions(self) -> list[LeafContribution]:
        """What each criterion adds, left to right."""
        structure = self.spec.structure
        return [] if structure is None else ablate(structure.root, self.leaves)

    @computed
    def question(self) -> str:
        """The card's one sentence, written from the counts."""
        size = (
            "a result the site did not count"
            if self.result_size is None
            else f"{self.result_size:,} genes"
        )
        kind = (
            "the separating strategy"
            if self.separates
            else "the closest strategy found"
        )
        return (
            f"Build {kind}: {_searches_words(len(self.leaves))} returning "
            f"{_returned_words(self.positive, 'positives')} and "
            f"{_returned_words(self.negative, 'negatives')} in {size}?"
        )

    def evidence(self) -> list[ControlTestEvidence]:
        """Every control result the offer holds: its read, then each leaf's."""
        return [self.read, *(leaf.controls for leaf in self.leaves)]

    def with_references_read(self, retrieved_as: RetrievedAs) -> SeparationOffer:
        """The offer with each reference the turn did not read taken off."""
        spec = self.spec.model_copy(
            update={
                "criteria": [
                    _read_references(c, retrieved_as) for c in self.spec.criteria
                ]
            }
        )
        return self.model_copy(update={"spec": spec})


class AttachedControls(CamelModel):
    """The controls an adopted strategy was measured against, saved as a set."""

    model_config = ConfigDict(frozen=True)

    # The separation run whose offer was adopted.
    task_id: str
    control_set_id: str
    positives: list[str]
    negatives: list[str]


SKIPPED_EXAMPLES = 8


class SeparationReport(CamelModel):
    """What one separation run measured, what it offers, and what it cost."""

    model_config = ConfigDict(frozen=True)

    task_id: str
    site_id: str
    mode: SeparationMode
    offer: SeparationOffer | None
    measured: list[MeasuredCriterion]
    skipped_by_reason: dict[SkipReason, int] = Field(default_factory=dict)
    skipped_examples: list[SkippedCriterion] = Field(
        default_factory=list, max_length=SKIPPED_EXAMPLES
    )
    unresolved_positive: list[str] = Field(default_factory=list)
    unresolved_negative: list[str] = Field(default_factory=list)
    shortfall: list[str] = Field(default_factory=list)
    charged_requests: int
    budget: int

    @computed
    def informative_count(self) -> int:
        """The measured searches that tell the positives from the negatives."""
        return sum(1 for m in self.measured if m.informs != "neither")

    @computed
    def summary(self) -> str:
        """One line of the result, from its counts."""
        offer = self.offer
        if offer is None:
            return f"no strategy assembled; {' '.join(self.shortfall)}"
        counts = (
            f"{_returned_words(offer.positive, 'positives')}, "
            f"{_returned_words(offer.negative, 'negatives')}, "
            + (
                "an uncounted result"
                if offer.result_size is None
                else f"{offer.result_size:,} genes"
            )
            + f", {_searches_words(len(offer.leaves))}"
        )
        cost = f"{self.charged_requests} of {self.budget} requests"
        if offer.separates:
            return f"{self.mode}: {counts}; {cost}"
        return f"no strategy separates the sets; closest: {counts}; {cost}"

    def with_references_read(self, retrieved_as: RetrievedAs) -> SeparationReport:
        """The report with each reference the turn did not read taken off."""
        return self.model_copy(
            update={
                "offer": None
                if self.offer is None
                else self.offer.with_references_read(retrieved_as),
                "measured": [
                    m.model_copy(
                        update={
                            "reference": None
                            if m.reference is None
                            else retrieved_as(m.reference)
                        }
                    )
                    for m in self.measured
                ],
            }
        )


def offers_evidence(
    offers: Mapping[str, SeparationOffer], task_ids: Iterable[str | None]
) -> list[ControlTestEvidence]:
    """Every control result the named offers hold, each offer once."""
    named = dict.fromkeys(task_id for task_id in task_ids if task_id is not None)
    return [
        tested
        for task_id in named
        if (offer := offers.get(task_id)) is not None
        for tested in offer.evidence()
    ]


__all__ = [
    "SEPARATION_BUDGET",
    "SEPARATION_BUDGET_MAX",
    "SEPARATION_BUDGET_MIN",
    "AttachedControls",
    "LeafContribution",
    "MeasuredCriterion",
    "OfferedLeaf",
    "RetrievedAs",
    "SeparationMode",
    "SeparationOffer",
    "SeparationReport",
    "SkippedCriterion",
    "ablate",
    "offers_evidence",
]
