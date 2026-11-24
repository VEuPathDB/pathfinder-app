"""The organism check: whether a result's records hold the organisms asked."""

from __future__ import annotations

from collections.abc import Sequence

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict

from strategist.domain.site_checks import CheckStatus, SiteCheck, UncheckedReason
from strategist.domain.strategy.constraints import ConstraintKind
from strategist.domain.strategy.organism_scope import SelectedOrganisms


class OrganismCount(CamelModel):
    model_config = ConfigDict(frozen=True)

    organism: str
    count: int


class UnreadOrganisms(CamelModel):
    model_config = ConfigDict(frozen=True)

    why: UncheckedReason
    evidence: str


class CountedOrganisms(CamelModel):
    model_config = ConfigDict(frozen=True)

    step: str
    total: int
    rows: list[OrganismCount]


def _listed(rows: Sequence[OrganismCount]) -> str:
    return ", ".join(f"{row.organism} ({row.count:,})" for row in rows)


def organism_check(
    subject: str,
    requirement: str,
    selected: SelectedOrganisms | None,
    read: CountedOrganisms | UnreadOrganisms | None,
    *,
    asked: str | None = None,
) -> SiteCheck:
    def judged(
        status: CheckStatus, evidence: str, why: UncheckedReason | None = None
    ) -> SiteCheck:
        return SiteCheck(
            kind=ConstraintKind.ORGANISM,
            subject=subject,
            status=status,
            evidence=evidence,
            requirement=requirement,
            why_unchecked=why,
        )

    match read:
        case UnreadOrganisms(why=why, evidence=evidence):
            return judged("unchecked", evidence, why)
        case CountedOrganisms() as found if selected is not None:
            pass
        case _:
            return judged(
                "unchecked",
                "no step of the strategy selects the organism of its result",
                "no_check",
            )
    if selected.unplaced:
        return judged(
            "unchecked",
            "the site's organism list could not be read, so the organisms under "
            f"{', '.join(sorted(selected.unplaced))} are not known",
            "no_check",
        )
    allowed = (
        selected
        if asked is None
        else SelectedOrganisms(entries=frozenset({asked}), taxa=selected.taxa)
    )
    whose = (
        "the strategy does not select"
        if asked is None
        else "the requirement does not name"
    )
    outside = [row for row in found.rows if not allowed.holds(row.organism)]
    if outside:
        held = sum(row.count for row in outside)
        return judged(
            "fail",
            f"{held:,} of the {found.total:,} records of {found.step} hold organisms "
            f"{whose}: {_listed(outside)}",
        )
    if sum(row.count for row in found.rows) < found.total:
        return judged(
            "unchecked",
            f"the site named the organisms of only some of the {found.total:,} "
            f"records of {found.step}",
            "no_check",
        )
    return judged(
        "pass",
        f"all {found.total:,} records of {found.step} hold an organism the "
        f"strategy selects: {_listed(found.rows)}",
    )


__all__ = ["CountedOrganisms", "OrganismCount", "UnreadOrganisms", "organism_check"]
