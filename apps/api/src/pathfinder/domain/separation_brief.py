"""What the Lead reads of one separation run: its counts, and no gene id."""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from veupathdb_mcp.separation import SkipReason

from pathfinder.domain.evidence import ControlSetEvidence
from pathfinder.domain.separation import (
    SeparationMode,
    SeparationOffer,
    SeparationReport,
)


class CriterionBrief(CamelModel):
    """One criterion of an offer, as the Lead reads it: its name and its counts."""

    model_config = ConfigDict(frozen=True)

    display_name: str
    positives_returned: int
    negatives_returned: int


class OfferBrief(CamelModel):
    """An offer as the Lead reads it: the card's question and the site's counts."""

    model_config = ConfigDict(frozen=True)

    question: str
    separates: bool
    positives_returned: int
    positive_controls: int
    negatives_returned: int
    negative_controls: int
    result_size: int | None
    criteria: list[CriterionBrief]


class SeparationBrief(CamelModel):
    """What the Lead reads of one separation run. It names no gene.

    The whole report rides the ``data-separation-result`` part for the card.
    """

    model_config = ConfigDict(frozen=True)

    task_id: str
    mode: SeparationMode
    summary: str
    offer: OfferBrief | None
    measured_count: int
    informative_count: int
    skipped_by_reason: dict[SkipReason, int]
    unresolved_positive_count: int
    unresolved_negative_count: int
    charged_requests: int
    budget: int


def _returned_count(tested: ControlSetEvidence | None) -> int:
    return 0 if tested is None else tested.returned_count


def _offer_brief(offer: SeparationOffer) -> OfferBrief:
    return OfferBrief(
        question=offer.question,
        separates=offer.separates,
        positives_returned=offer.positive.returned_count,
        positive_controls=offer.positive.controls_count,
        negatives_returned=offer.negative.returned_count,
        negative_controls=offer.negative.controls_count,
        result_size=offer.result_size,
        criteria=[
            CriterionBrief(
                display_name=leaf.display_name,
                positives_returned=_returned_count(leaf.controls.positive),
                negatives_returned=_returned_count(leaf.controls.negative),
            )
            for leaf in offer.leaves
        ],
    )


def brief_of(report: SeparationReport) -> SeparationBrief:
    """The run as the Lead reads it: the counts and no control id."""
    return SeparationBrief(
        task_id=report.task_id,
        mode=report.mode,
        summary=report.summary,
        offer=None if report.offer is None else _offer_brief(report.offer),
        measured_count=len(report.measured),
        informative_count=report.informative_count,
        skipped_by_reason=report.skipped_by_reason,
        unresolved_positive_count=len(report.unresolved_positive),
        unresolved_negative_count=len(report.unresolved_negative),
        charged_requests=report.charged_requests,
        budget=report.budget,
    )


__all__ = ["CriterionBrief", "OfferBrief", "SeparationBrief", "brief_of"]
