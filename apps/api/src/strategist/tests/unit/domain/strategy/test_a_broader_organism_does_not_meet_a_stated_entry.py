"""An organism requirement is met by its entry or entries under it, never a broader node."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue

from strategist.domain.site_checks import (
    CountedOrganisms,
    OrganismCount,
    organism_check,
)
from strategist.domain.strategy.constraint_grounding import ground_against_spec
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    OrganismValue,
)
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    RequirementLink,
)
from strategist.domain.strategy.organism_scope import SelectedOrganisms, SiteTaxa

PF3 = "Plasmodium falciparum 3D7"
SPECIES = "Plasmodium falciparum"
_STRAIN = Constraint(
    id="d4acbf561ea7",
    kind=ConstraintKind.ORGANISM,
    requested_value=PF3,
    label=PF3,
    source=ConstraintSource.USER_EXPLICIT,
    quote=PF3,
    value=OrganismValue(organism=PF3),
)


def _bound_on(organism: str) -> OperationalSpec:
    """The n4 step: 30 to 99 transmembrane domains on the organism FRAME bound."""
    return OperationalSpec(
        criteria=[
            Criterion(
                id="c_tm_domains",
                text="30 to 99 transmembrane domains",
                search_name="GenesByTransmembraneDomains",
                organism_param="organism",
                answers=[RequirementLink(requirement=_STRAIN.id, param="organism")],
                resolved_params={
                    "organism": BoundValue(
                        value=MultiPickValue(values=[organism]), source="stated"
                    )
                },
            )
        ]
    )


def test_the_species_bound_for_a_stated_strain_is_not_the_strain() -> None:
    [grounded] = ground_against_spec([_STRAIN], _bound_on(SPECIES))

    assert (grounded.status, grounded.realized_value, grounded.blocks) == (
        ConstraintStatus.SUBSTITUTED,
        SPECIES,
        True,
    )


def test_the_stated_strain_bound_meets_it() -> None:
    [grounded] = ground_against_spec([_STRAIN], _bound_on(PF3))

    assert (grounded.status, grounded.realized_value) == (
        ConstraintStatus.GROUNDED,
        PF3,
    )


def test_the_check_reads_the_rows_against_the_stated_entry() -> None:
    taxa = SiteTaxa(
        under={
            SPECIES: frozenset(
                {PF3, "Plasmodium falciparum 7G8", "Plasmodium falciparum Dd2"}
            )
        }
    )
    selected = SelectedOrganisms(entries=frozenset({SPECIES}), taxa=taxa)
    read = CountedOrganisms(
        step="c_tm",
        total=174,
        rows=[
            OrganismCount(organism=PF3, count=9),
            OrganismCount(organism="Plasmodium falciparum 7G8", count=83),
            OrganismCount(organism="Plasmodium falciparum Dd2", count=82),
        ],
    )

    check = organism_check(PF3, _STRAIN.id, selected, read, asked=PF3)

    assert (check.status, check.evidence) == (
        "fail",
        (
            "165 of the 174 records of c_tm hold organisms the requirement does "
            "not name: Plasmodium falciparum 7G8 (83), Plasmodium falciparum Dd2 (82)"
        ),
    )
