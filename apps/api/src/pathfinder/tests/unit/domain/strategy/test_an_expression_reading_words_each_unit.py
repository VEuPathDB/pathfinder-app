from __future__ import annotations

import pytest
from veupathdb.domain.parameters import PhyleticTree

from pathfinder.domain.strategy.expression_handles import (
    READING_LIMIT,
    expression_reading,
)
from pathfinder.tests._support.ortho_taxonomy import (
    labelled_genomes,
    recorded_ortho_taxonomy,
)

_TREE = recorded_ortho_taxonomy()
_PLASMODIUM = labelled_genomes(_TREE, "Plasmodium ")
_TOXOPLASMA = labelled_genomes(_TREE, "Toxoplasma ")
_CRYPTOSPORIDIUM = labelled_genomes(_TREE, "Cryptosporidium ")


def _read(text: str) -> str:
    return expression_reading(text, _TREE)


def _genome_codes(count: int) -> list[str]:
    return [node.code for node in _TREE.nodes() if not node.clade][:count]


def _unplaced(count: int) -> list[str]:
    return [f"z{chr(97 + n // 26)}{chr(97 + n % 26)}" for n in range(count)]


def test_a_list_of_several_species_is_named_when_it_covers_no_group() -> None:
    species = [
        *_TREE.species_groups(_CRYPTOSPORIDIUM)[:2],
        *_TREE.species_groups(_TOXOPLASMA),
    ]
    text = " AND ".join(f"{'+'.join(one.genomes)}=0T" for one in species) + (
        f" AND {'+'.join(_PLASMODIUM)}>=1T"
    )

    assert _read(text) == (
        "no genome in any of 3 species (17 genomes: Cryptosporidium andersoni, "
        "Cryptosporidium bovis, Toxoplasma gondii) and at least 1 of the 61 genomes "
        "of Plasmodium"
    )


def test_each_of_a_genus_and_more_names_both() -> None:
    species = [*_TREE.species_groups(_PLASMODIUM), *_TREE.species_groups(_TOXOPLASMA)]
    text = " AND ".join(f"{'+'.join(one.genomes)}>=1T" for one in species)

    assert _read(text) == (
        "at least 1 genome in each of 24 species (76 genomes: the 23 species of "
        "Plasmodium, Toxoplasma gondii)"
    )


def test_two_whole_groups_are_both_named_with_their_total() -> None:
    both = "+".join([*_PLASMODIUM, *_CRYPTOSPORIDIUM])

    assert _read(f"{both}>=2T AND {'+'.join(_TOXOPLASMA)}=0T") == (
        "at least 2 of the 79 genomes of Plasmodium, Cryptosporidium and none of the "
        "15 genomes of Toxoplasma gondii"
    )


def test_genomes_outside_one_group_list_each_piece_with_its_size() -> None:
    held = "+".join([*_PLASMODIUM, "tgon", "tgve", _CRYPTOSPORIDIUM[0]])

    assert _read(f"{held}>=2T AND {'+'.join(_CRYPTOSPORIDIUM[1:])}=0T").startswith(
        "at least 2 of these 64 (Plasmodium (all 61), Cryptosporidium andersoni "
        "isolate 30847, 2 of the 15 genomes of Toxoplasma gondii: ME49, VEG) and "
    )


@pytest.mark.parametrize(
    ("unit", "words"),
    [
        ("{g}<=1T", "exactly 1 of the 61 genomes of Plasmodium"),
        ("{g}<2T", "exactly 1 of the 61 genomes of Plasmodium"),
        ("{g}<5T", "1 to 4 of the 61 genomes of Plasmodium"),
        ("{g}<=5T", "1 to 5 of the 61 genomes of Plasmodium"),
        ("{g}>5T", "more than 5 of the 61 genomes of Plasmodium"),
        ("{g}=5T", "exactly 5 of the 61 genomes of Plasmodium"),
        ("{g}>=61T", "all of the 61 genomes of Plasmodium"),
        ("{g}=61T", "all of the 61 genomes of Plasmodium"),
        ("{g}=0", "no protein in the 61 genomes of Plasmodium"),
        ("{g}<=1", "exactly 1 protein in the 61 genomes of Plasmodium"),
        ("{g}>=2", "at least 2 proteins in the 61 genomes of Plasmodium"),
        ("{g}<=0T", "at most 0 of the 61 genomes of Plasmodium"),
    ],
)
def test_each_operator_reads_as_the_site_counts_it(unit: str, words: str) -> None:
    text = f"{unit.format(g='+'.join(_PLASMODIUM))} AND {'+'.join(_TOXOPLASMA)}=0T"

    assert _read(text) == f"{words} and none of the 15 genomes of Toxoplasma gondii"


@pytest.mark.parametrize(
    ("unit", "words"),
    [
        ("tgon=0T", "no protein in Toxoplasma gondii ME49"),
        ("tgon=0", "no protein in Toxoplasma gondii ME49"),
        ("tgon>=1T", "at least 1 genome of Toxoplasma gondii ME49"),
        ("tgon>=3", "at least 3 proteins in Toxoplasma gondii ME49"),
    ],
)
def test_one_genome_reads_by_its_label(unit: str, words: str) -> None:
    text = f"{unit} AND {'+'.join(_PLASMODIUM)}=0T"

    assert _read(text) == f"{words} and none of the 61 genomes of Plasmodium"


def test_a_genome_short_of_its_species_stays_out_of_the_species_fold() -> None:
    text = f"padl>=1T AND pber>=1T AND pfal>=1T AND {'+'.join(_TOXOPLASMA)}=0T"

    assert _read(text) == (
        "at least 1 genome in each of 2 species (2 genomes: Plasmodium adleri, "
        "Plasmodium berghei) and at least 1 genome of Plasmodium falciparum 3D7 and "
        "none of the 15 genomes of Toxoplasma gondii"
    )


def test_a_count_as_large_as_the_list_is_all_only_when_it_requires_all() -> None:
    plasmodium = "+".join(_PLASMODIUM)

    assert _read(f"{plasmodium}<=61T AND {'+'.join(_TOXOPLASMA)}=0T").startswith(
        "1 to 61 of the 61 genomes of Plasmodium and "
    )


def test_a_protein_count_per_species_reads_in_each() -> None:
    two = [g for g in _TREE.species_groups(_PLASMODIUM) if len(g.genomes) == 2]
    text = " AND ".join(f"{'+'.join(one.genomes)}<=1" for one in two) + (
        f" AND {'+'.join(_TOXOPLASMA)}=0T"
    )

    assert _read(text).startswith(
        f"exactly 1 protein in each of {len(two)} species ({2 * len(two)} genomes: "
    )


def test_no_protein_per_species_reads_in_any() -> None:
    species = [
        *_TREE.species_groups(_TOXOPLASMA),
        *_TREE.species_groups(_CRYPTOSPORIDIUM),
    ]
    text = " AND ".join(f"{'+'.join(one.genomes)}=0" for one in species[:2]) + (
        f" AND {'+'.join(_PLASMODIUM)}>=1T"
    )

    assert _read(text).startswith("no protein in any of 2 species (")


def _triples(codes: list[str]) -> str:
    return " OR ".join(
        f"{first}>=1T AND {second}=0T AND {third}>=2"
        for first, second, third in zip(
            codes[::3], codes[1::3], codes[2::3], strict=True
        )
    )


def test_terms_past_the_limit_read_by_the_first_and_the_last() -> None:
    text = _triples(_genome_codes(120))
    reading = _read(text)

    assert reading.startswith(
        f"names 120 codes in 40 OR terms of 3 AND clauses, {len(text):,} characters; "
        "first term: at least 1 genome of "
    )
    assert "; last term: at least 1 genome of " in reading
    assert len(reading) <= READING_LIMIT


def test_terms_of_different_sizes_state_the_range_of_sizes() -> None:
    codes = _genome_codes(121)
    text = f"{_triples(codes[:120])} OR {codes[120]}>=1T"

    assert _read(text).startswith(
        f"names 121 codes in 41 OR terms of 1 to 3 AND clauses, {len(text):,} characters;"
    )


def test_codes_no_tree_places_read_as_written() -> None:
    assert expression_reading("aaa+bbb>=1T AND ccc=0T", PhyleticTree()) == (
        "at least 1 genome of these 2: aaa, bbb and exactly 0 genomes of ccc"
    )
    text = " AND ".join(f"{'+'.join(_unplaced(30))}>={n}T" for n in (1, 2))

    assert expression_reading(text, PhyleticTree()).startswith(
        "at least 1 of these 30 (zaa, zab, "
    )


def test_a_clause_with_one_code_no_tree_places_names_the_code() -> None:
    text = " AND ".join(f"{code}=0 AND {code}>=2T" for code in _unplaced(12))

    assert expression_reading(text, PhyleticTree()).startswith(
        "no protein in zaa and at least 2 genomes of zaa and "
    )


def test_terms_too_long_to_quote_still_name_the_shape() -> None:
    codes = _unplaced(150)
    text = " OR ".join(" AND ".join(f"{c}>={n}T" for c in codes) for n in (1, 2, 3))

    assert expression_reading(text, PhyleticTree()) == (
        f"names 150 codes in 3 OR terms of 150 AND clauses, {len(text):,} characters"
    )


def test_an_and_past_the_limit_states_what_its_clauses_require() -> None:
    codes = _unplaced(300)
    text = " AND ".join(
        [
            *(f"{code}>=1T" for code in codes[:298]),
            f"{codes[298]}=0T",
            f"{codes[299]}<=4",
        ]
    )

    assert expression_reading(text, PhyleticTree()) == (
        f"names 300 codes in 300 AND clauses, {len(text):,} characters: 298 of at "
        "least 1 genome, 1 of no genome, 1 of 1 to 4 proteins"
    )


def test_an_and_with_more_kinds_than_the_limit_holds_names_only_the_shape() -> None:
    codes = _unplaced(600)
    text = " AND ".join(f"{code}>={n}T" for n, code in enumerate(codes, start=1))

    assert expression_reading(text, PhyleticTree()) == (
        f"names 600 codes in 600 AND clauses, {len(text):,} characters"
    )
