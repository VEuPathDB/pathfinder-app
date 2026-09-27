"""An organism entry the message states whole is one requirement."""

from __future__ import annotations

import pytest

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.organism_phrases import (
    complete_organisms,
    stated_organisms,
)
from pathfinder.tests._support.site_organisms import recorded_organisms

PEST = (
    "Find Anopheles gambiae PEST genes with a predicted signal peptide and 2 to 99 "
    "transmembrane domains."
)
NEOSPORA = "Carry these to their orthologs in Neospora caninum Liverpool."
IOWA = "Find Cryptosporidium parvum Iowa II genes with a signal peptide"
S2 = {
    "plasmodb": ("Plasmodium falciparum 3D7", "Find Plasmodium falciparum 3D7 genes"),
    "toxodb": ("Toxoplasma gondii ME49", "Find Toxoplasma gondii ME49 genes"),
    "fungidb": (
        "Aspergillus fumigatus Af293",
        "Find Aspergillus fumigatus Af293 genes",
    ),
}
S2_TAIL = " with a predicted signal peptide and 2 to 99 transmembrane domains."


def _stated(kind: ConstraintKind, value: str) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        label=value,
        source=ConstraintSource.USER_EXPLICIT,
    )


def _organism(value: str) -> Constraint:
    return _stated(ConstraintKind.ORGANISM, value)


def _other(value: str) -> Constraint:
    return _stated(ConstraintKind.OTHER, value)


def _completed(
    site: str, message: str, *constraints: Constraint
) -> tuple[list[tuple[str, str]], list[str]]:
    completed, notes = complete_organisms(
        list(constraints), message, recorded_organisms(site)
    )
    return [(c.kind.value, c.requested_value) for c in completed], notes


def _recorded(entry: str) -> str:
    return f'organism recorded as "{entry}"'


def test_the_strain_is_part_of_the_entry_the_message_states() -> None:
    [stated] = stated_organisms(PEST, recorded_organisms("vectorbase"))

    assert stated.entry == "Anopheles gambiae PEST"
    assert (stated.start, stated.end) == (1, 4)


def test_the_longest_entry_at_a_position_wins() -> None:
    message = "Find Neospora caninum Liverpool 2019 genes"

    [stated] = stated_organisms(message, recorded_organisms("toxodb"))

    assert stated.entry == "Neospora caninum Liverpool 2019"


def test_a_genus_written_as_an_initial_states_the_entry() -> None:
    message = "Find P. falciparum 3D7 genes with a signal peptide"

    [stated] = stated_organisms(message, recorded_organisms("plasmodb"))

    assert stated.entry == "Plasmodium falciparum 3D7"


def test_a_species_without_its_strain_states_no_entry() -> None:
    message = "Find Plasmodium falciparum genes with a signal peptide"

    assert stated_organisms(message, recorded_organisms("plasmodb")) == []


def test_the_split_organism_is_completed_and_the_strain_constraint_kept() -> None:
    completed, notes = _completed(
        "vectorbase",
        PEST,
        _organism("Anopheles gambiae"),
        _stated(
            ConstraintKind.COMBINATION,
            "PEST genes AND genes with a predicted signal peptide",
        ),
        _other("PEST genes"),
        _other("predicted signal peptide"),
    )

    assert completed == [
        ("organism", "Anopheles gambiae PEST"),
        ("combination", "PEST genes AND genes with a predicted signal peptide"),
        ("other", "PEST genes"),
        ("other", "predicted signal peptide"),
    ]
    assert notes == [_recorded("Anopheles gambiae PEST")]


def test_the_species_recorded_without_its_strain_is_completed() -> None:
    completed, notes = _completed("toxodb", NEOSPORA, _organism("Neospora caninum"))

    assert completed == [("organism", "Neospora caninum Liverpool")]
    assert notes == [_recorded("Neospora caninum Liverpool")]


def test_the_strain_recorded_as_a_requirement_of_its_own_is_left_as_stated() -> None:
    completed, notes = _completed(
        "toxodb", NEOSPORA, _organism("Neospora caninum"), _other("Liverpool strain")
    )

    assert completed == [
        ("organism", "Neospora caninum Liverpool"),
        ("other", "Liverpool strain"),
    ]
    assert notes == [_recorded("Neospora caninum Liverpool")]


@pytest.mark.parametrize(
    ("constraints", "recorded"),
    [
        ([_organism("Cryptosporidium parvum")], ["Cryptosporidium parvum Iowa II"]),
        ([_organism("C. parvum Iowa")], ["Cryptosporidium parvum Iowa II"]),
        ([_organism("Cryptosporidium parvum Iowa II"), _other("Iowa isolate")], []),
        ([_organism("Cryptosporidium parvum Iowa II"), _other("II")], []),
    ],
)
def test_every_prefix_of_a_two_word_strain_completes_to_the_entry(
    constraints: list[Constraint], recorded: list[str]
) -> None:
    completed, notes = _completed("cryptodb", IOWA, *constraints)

    assert completed[0] == ("organism", "Cryptosporidium parvum Iowa II")
    assert completed[1:] == [(c.kind.value, c.requested_value) for c in constraints[1:]]
    assert notes == [_recorded(entry) for entry in recorded]


def test_the_whole_entry_and_the_other_requirements_pass() -> None:
    completed, notes = _completed(
        "cryptodb",
        IOWA,
        _organism("Cryptosporidium parvum Iowa II"),
        _other("signal peptide"),
    )

    assert completed == [
        ("organism", "Cryptosporidium parvum Iowa II"),
        ("other", "signal peptide"),
    ]
    assert notes == []


@pytest.mark.parametrize("site", sorted(S2))
def test_the_standard_prompts_pass_untouched(site: str) -> None:
    entry, head = S2[site]
    message = head + S2_TAIL
    stated = [
        _organism(entry),
        _stated(
            ConstraintKind.COMBINATION,
            "predicted signal peptide AND 2 to 99 transmembrane domains",
        ),
        _other("predicted signal peptide"),
        _other("2 to 99 transmembrane domains"),
        _stated(ConstraintKind.RECORD_TYPE, "genes"),
    ]

    completed, notes = complete_organisms(stated, message, recorded_organisms(site))

    assert [s.entry for s in stated_organisms(message, recorded_organisms(site))] == [
        entry
    ]
    assert completed == stated
    assert notes == []


def test_the_orthology_constraint_that_names_the_source_organism_is_untouched() -> None:
    message = "Carry these to their orthologs in Plasmodium vivax P01."
    orthology = _stated(
        ConstraintKind.OTHER,
        "orthologs of the current Plasmodium falciparum 3D7 signal-peptide and "
        "2 to 99 transmembrane-domain genes",
    )
    stated = [_organism("Plasmodium vivax P01"), orthology]

    completed, notes = complete_organisms(
        stated, message, recorded_organisms("plasmodb")
    )

    assert completed == stated
    assert notes == []


def test_a_comparator_that_names_two_whole_entries_passes() -> None:
    message = (
        "Find genes that differ between Plasmodium falciparum 3D7 and "
        "Plasmodium falciparum HB3"
    )
    stated = [
        _organism("Plasmodium falciparum 3D7"),
        _organism("Plasmodium falciparum HB3"),
        _stated(ConstraintKind.COMPARATOR, "P. falciparum 3D7 vs P. falciparum HB3"),
    ]

    completed, notes = complete_organisms(
        stated, message, recorded_organisms("plasmodb")
    )

    assert [
        s.entry for s in stated_organisms(message, recorded_organisms("plasmodb"))
    ] == [
        "Plasmodium falciparum 3D7",
        "Plasmodium falciparum HB3",
    ]
    assert completed == stated
    assert notes == []


def test_an_organism_the_message_does_not_state_whole_is_left_as_recorded() -> None:
    message = "Find Plasmodium falciparum genes with a signal peptide"

    completed, notes = _completed(
        "plasmodb", message, _organism("Plasmodium falciparum")
    )

    assert completed == [("organism", "Plasmodium falciparum")]
    assert notes == []


def test_the_strain_as_a_term_of_the_combination_is_left_as_stated() -> None:
    combination = (
        "PEST genes AND predicted signal peptide AND 2 to 99 transmembrane domains"
    )

    completed, notes = _completed(
        "vectorbase",
        PEST,
        _organism("Anopheles gambiae PEST"),
        _stated(ConstraintKind.COMBINATION, combination),
    )

    assert completed == [
        ("organism", "Anopheles gambiae PEST"),
        ("combination", combination),
    ]
    assert notes == []
