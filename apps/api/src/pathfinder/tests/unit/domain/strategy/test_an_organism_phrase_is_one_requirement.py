"""An organism entry the message states whole is one requirement."""

from __future__ import annotations

import pytest

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.organism_phrases import (
    organism_split_refusal,
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


def _sentence(entry: str, words: str) -> str:
    return (
        f'The message names the organism "{entry}", one entry of this site\'s '
        "organism list. Record it whole as the organism constraint; "
        f'"{words}" is part of its name, not a requirement of its own.'
    )


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


def _refusal(site: str, message: str, *constraints: Constraint) -> str | None:
    stated = stated_organisms(message, recorded_organisms(site))
    return organism_split_refusal(list(constraints), message, stated)


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


def test_a_requirement_built_from_the_strain_is_refused() -> None:
    refusal = _refusal(
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

    assert refusal == _sentence("Anopheles gambiae PEST", "PEST")


def test_the_species_recorded_without_its_strain_is_refused() -> None:
    refusal = _refusal("toxodb", NEOSPORA, _organism("Neospora caninum"))

    assert refusal == _sentence("Neospora caninum Liverpool", "Liverpool")


def test_the_strain_recorded_as_a_requirement_of_its_own_is_refused() -> None:
    refusal = _refusal(
        "toxodb", NEOSPORA, _organism("Neospora caninum"), _other("Liverpool strain")
    )

    assert refusal == _sentence("Neospora caninum Liverpool", "Liverpool")


@pytest.mark.parametrize(
    ("constraints", "words"),
    [
        ([_organism("Cryptosporidium parvum")], "Iowa II"),
        ([_organism("C. parvum Iowa")], "II"),
        ([_organism("Cryptosporidium parvum Iowa II"), _other("Iowa isolate")], "Iowa"),
        ([_organism("Cryptosporidium parvum Iowa II"), _other("II")], "II"),
    ],
)
def test_every_part_of_a_two_word_strain_is_held_to_the_entry(
    constraints: list[Constraint], words: str
) -> None:
    refusal = _refusal("cryptodb", IOWA, *constraints)

    assert refusal == _sentence("Cryptosporidium parvum Iowa II", words)


def test_the_whole_entry_and_the_other_requirements_pass() -> None:
    stated = stated_organisms(IOWA, recorded_organisms("cryptodb"))
    constraints = [
        _organism("Cryptosporidium parvum Iowa II"),
        _other("signal peptide"),
    ]

    refusal = organism_split_refusal(constraints, IOWA, stated)

    assert [s.entry for s in stated] == ["Cryptosporidium parvum Iowa II"]
    assert refusal is None


@pytest.mark.parametrize("site", sorted(S2))
def test_the_standard_prompts_pass_untouched(site: str) -> None:
    entry, head = S2[site]
    message = head + S2_TAIL

    refusal = _refusal(
        site,
        message,
        _organism(entry),
        _stated(
            ConstraintKind.COMBINATION,
            "predicted signal peptide AND 2 to 99 transmembrane domains",
        ),
        _other("predicted signal peptide"),
        _other("2 to 99 transmembrane domains"),
        _stated(ConstraintKind.RECORD_TYPE, "genes"),
    )

    assert [s.entry for s in stated_organisms(message, recorded_organisms(site))] == [
        entry
    ]
    assert refusal is None


def test_a_word_the_message_also_holds_outside_the_entry_is_a_requirement() -> None:
    message = "Find Anopheles gambiae PEST genes that other PEST strains lack"

    stated = stated_organisms(message, recorded_organisms("vectorbase"))
    constraints = [
        _organism("Anopheles gambiae PEST"),
        _other("absent from other PEST strains"),
    ]

    refusal = organism_split_refusal(constraints, message, stated)

    assert [(s.entry, s.start, s.end) for s in stated] == [
        ("Anopheles gambiae PEST", 1, 4)
    ]
    assert refusal is None


def test_a_comparator_that_names_two_whole_entries_passes() -> None:
    message = (
        "Find genes that differ between Plasmodium falciparum 3D7 and "
        "Plasmodium falciparum HB3"
    )
    stated = stated_organisms(message, recorded_organisms("plasmodb"))
    constraints = [
        _organism("Plasmodium falciparum 3D7"),
        _organism("Plasmodium falciparum HB3"),
        _stated(ConstraintKind.COMPARATOR, "P. falciparum 3D7 vs P. falciparum HB3"),
    ]

    refusal = organism_split_refusal(constraints, message, stated)

    assert [s.entry for s in stated] == [
        "Plasmodium falciparum 3D7",
        "Plasmodium falciparum HB3",
    ]
    assert refusal is None


def test_a_requirement_that_names_the_whole_entry_passes() -> None:
    stated = stated_organisms(NEOSPORA, recorded_organisms("toxodb"))
    constraints = [_other("orthologs in Neospora caninum Liverpool")]

    refusal = organism_split_refusal(constraints, NEOSPORA, stated)

    assert [s.entry for s in stated] == ["Neospora caninum Liverpool"]
    assert refusal is None


def test_the_strain_as_a_term_of_the_combination_is_refused() -> None:
    refusal = _refusal(
        "vectorbase",
        PEST,
        _organism("Anopheles gambiae PEST"),
        _stated(
            ConstraintKind.COMBINATION,
            "PEST genes AND predicted signal peptide AND 2 to 99 transmembrane domains",
        ),
    )

    assert refusal == _sentence("Anopheles gambiae PEST", "PEST")
