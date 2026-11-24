"""An organism requirement is judged on the step that links it, else on the result
against every organism the requirements name."""

from __future__ import annotations

from strategist.domain.organism_checks import (
    CountedOrganisms,
    OrganismAsked,
    OrganismCount,
    organism_check,
)
from strategist.domain.site_checks import SiteCheck
from strategist.domain.strategy.organism_scope import SelectedOrganisms, SiteTaxa

PF3 = "Plasmodium falciparum 3D7"
PV = "Plasmodium vivax P01"
_BOTH = SelectedOrganisms(entries=frozenset({PF3, PV}), taxa=SiteTaxa())
_NAMES = {"pf3": PF3, "pv": PV, "pf7": "Plasmodium falciparum 7G8"}


def _rows(**counts: int) -> CountedOrganisms:
    rows = [OrganismCount(organism=_NAMES[k], count=n) for k, n in counts.items()]
    return CountedOrganisms(step="union", total=sum(counts.values()), rows=rows)


def _unlinked(entry: str, read: CountedOrganisms, *named: str) -> SiteCheck:
    asked = OrganismAsked(entry=entry, named=frozenset(named), linked=False)
    return organism_check(entry, f"r_{entry}", _BOTH, read, asked=asked)


def test_a_union_of_two_asked_strains_passes_each_requirement() -> None:
    read = _rows(pf3=150, pv=250)

    checks = [_unlinked(entry, read, PF3, PV) for entry in (PF3, PV)]

    assert [c.status for c in checks] == ["pass", "pass"]


def test_a_strain_and_its_orthologs_in_another_pass_the_strain() -> None:
    assert _unlinked(PF3, _rows(pf3=120, pv=80), PF3, PV).status == "pass"


def test_a_result_holding_no_record_of_the_entry_fails_it() -> None:
    check = _unlinked(PF3, _rows(pv=80), PF3, PV)

    assert (check.status, check.evidence) == (
        "fail",
        f"none of the 80 records of union is of {PF3}",
    )


def test_a_record_no_requirement_names_fails_the_unlinked_check() -> None:
    check = _unlinked(PF3, _rows(pf3=9, pf7=83), PF3)

    assert (check.status, check.evidence) == (
        "fail",
        (
            "83 of the 92 records of union hold organisms no requirement names: "
            "Plasmodium falciparum 7G8 (83)"
        ),
    )
