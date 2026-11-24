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


class OrganismAsked(CamelModel):
    """The organism requirement a check judges: its entry, every organism the
    requirements name, and whether a step links it."""

    model_config = ConfigDict(frozen=True)

    entry: str
    named: frozenset[str]
    linked: bool

    @property
    def allowed(self) -> frozenset[str]:
        return frozenset({self.entry}) if self.linked else self.named

    @property
    def whose(self) -> str:
        return (
            "the requirement does not name" if self.linked else "no requirement names"
        )


def _misplaced(
    found: CountedOrganisms, judged_by: SelectedOrganisms, asked: OrganismAsked | None
) -> str | None:
    """Why the rows fail: none of the asked entry, or rows outside what is allowed."""
    if asked is not None and not asked.linked:
        own = SelectedOrganisms(entries=frozenset({asked.entry}), taxa=judged_by.taxa)
        if not any(own.holds(row.organism) for row in found.rows if row.count):
            return f"none of the {found.total:,} records of {found.step} is of {asked.entry}"
    outside = [row for row in found.rows if not judged_by.holds(row.organism)]
    if not outside:
        return None
    whose = "the strategy does not select" if asked is None else asked.whose
    held = sum(row.count for row in outside)
    return (
        f"{held:,} of the {found.total:,} records of {found.step} hold organisms "
        f"{whose}: {_listed(outside)}"
    )


def organism_check(
    subject: str,
    requirement: str,
    selected: SelectedOrganisms | None,
    read: CountedOrganisms | UnreadOrganisms | None,
    *,
    asked: OrganismAsked | None = None,
) -> SiteCheck:
    """The result's organisms against the strategy's selection; with ``asked``, a
    linked requirement against its step's records and an unlinked one against the
    result and every organism the requirements name."""

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
    judged_by = (
        selected
        if asked is None
        else SelectedOrganisms(entries=asked.allowed, taxa=selected.taxa)
    )
    misplaced = _misplaced(found, judged_by, asked)
    if misplaced is not None:
        return judged("fail", misplaced)
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


__all__ = [
    "CountedOrganisms",
    "OrganismAsked",
    "OrganismCount",
    "UnreadOrganisms",
    "organism_check",
]
