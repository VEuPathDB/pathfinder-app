from __future__ import annotations

from pathlib import Path

import pytest
from veupathdb.domain.parameters import PhyleticExpression

from pathfinder.domain.strategy.expression_handles import (
    READING_LIMIT,
    expression_reading,
)
from pathfinder.evals.case import EvalCase
from pathfinder.evals.store import CORPUS_DIR
from pathfinder.tests._support.ortho_taxonomy import (
    labelled_genomes,
    recorded_ortho_taxonomy,
)

_TREE = recorded_ortho_taxonomy()
_PHYLETIC = "GroupsByPhyleticPattern"

_PLASMODIUM = labelled_genomes(_TREE, "Plasmodium ")
_TOXOPLASMA = labelled_genomes(_TREE, "Toxoplasma ")
_CRYPTOSPORIDIUM = labelled_genomes(_TREE, "Cryptosporidium ")
_FALCIPARUM = labelled_genomes(_TREE, "Plasmodium falciparum ")

_EACH_SPECIES = (
    "padl>=1T AND pber>=1T AND pbil>=1T AND pblg>=1T AND pbbi>=1T AND pcha+pccb>=1T "
    "AND pcoa>=1T AND pcyn+pcym>=1T AND pfal+pfag+pfsg+pfac+pfad+pfga+pfgb+pfgn+pfhb"
    "+pfai+pfke+pfkh+pfkt+pfml+pfnc+pfng+pfnf+pfsd+pfsn+pftg>=1T AND pfra>=1T AND "
    "pgab+pgas>=1T AND pgal>=1T AND pinu>=1T AND pkah+pkno+pknp>=1T AND pmal>=1T AND "
    "pova+powp>=1T AND ppra>=1T AND prei+preg>=1T AND prel>=1T AND pvbd+pvce+pvld+"
    "pvcr+pvpc+pvvc+pvin>=1T AND pvlk>=1T AND pvip+pvpv+pvpw+pviv>=1T AND pyoe+pyxn+"
    "pyyx+pyoy>=1T AND tgar+tgca+tgco+tgfo+tggd+tggt+tgma+tgon+tgop+tgee+tgru+tgta+"
    "tgtg+tgva+tgve=0T"
)
_MORE_IN_ONE_GENOME = " OR ".join(f"pfal={n} AND tgon>={n + 1}" for n in range(112))


def _corpus_writings(case: str) -> list[str]:
    path = CORPUS_DIR / f"{case}.json"
    expected = EvalCase.model_validate_json(path.read_text()).expected
    return expected.expressions[_PHYLETIC]


def _read(text: str) -> str:
    return expression_reading(text, _TREE)


def _holds(text: str, proteins: dict[str, int]) -> bool:
    return PhyleticExpression.parse(text).holds_for(proteins, _TREE)


def _one_genome_per_species() -> dict[str, int]:
    return {group.genomes[0]: 1 for group in _TREE.species_groups(_PLASMODIUM)}


def test_one_genome_per_species_reads_as_that_and_not_as_every_genome() -> None:
    assert _read(_EACH_SPECIES) == (
        "at least 1 genome in each of the 23 species of Plasmodium (61 genomes) "
        "and none of the 15 genomes of Toxoplasma gondii"
    )
    profile = _one_genome_per_species()
    assert (len(profile), _holds(_EACH_SPECIES, profile)) == (23, True)


def test_the_reading_is_false_of_a_species_missing_or_a_toxoplasma_genome() -> None:
    profile = _one_genome_per_species()
    missing = {code: n for code, n in profile.items() if code != "padl"}

    assert (
        _holds(_EACH_SPECIES, missing),
        _holds(_EACH_SPECIES, {**profile, "tgon": 1}),
    ) == (False, False)


def test_a_count_comparison_reads_as_the_comparison_and_its_range() -> None:
    assert _read(_MORE_IN_ONE_GENOME) == (
        "at least 1 more protein in Toxoplasma gondii ME49 than in Plasmodium "
        "falciparum 3D7, while Plasmodium falciparum 3D7 holds 0 to 111 proteins "
        "(112 OR terms)"
    )
    assert [
        _holds(_MORE_IN_ONE_GENOME, proteins)
        for proteins in (
            {"tgon": 1},
            {"pfal": 3, "tgon": 4},
            {"pfal": 3, "tgon": 3},
            {"pfal": 112, "tgon": 500},
        )
    ] == [True, True, False, False]


def test_parentheses_the_site_drops_read_the_same() -> None:
    [written, stored] = _corpus_writings(
        "orthomcl-more-proteins-in-one-genome-than-another"
    )

    assert _read(written) == _read(stored)
    assert _read(written).startswith("at least 1 more protein in ")


def test_stepped_bands_read_band_by_band() -> None:
    [written] = _corpus_writings(
        "orthomcl-expanded-in-toxoplasma-over-plasmodium-in-bands"
    )

    assert _read(written) == (
        "4 bands of the proteins in the 61 genomes of Plasmodium, each with a floor "
        "on the proteins in the 15 genomes of Toxoplasma gondii: 122 to 182 with at "
        "least 60; 183 to 243 with at least 90; 244 to 304 with at least 120; 305 to "
        "365 with at least 150"
    )


def test_a_gap_in_the_steps_lists_the_bands_and_not_a_range() -> None:
    text = " OR ".join(
        f"{'+'.join(_PLASMODIUM)}={n} AND {'+'.join(_TOXOPLASMA)}>={n + 2}"
        for n in (1, 2, 4)
    )

    assert _read(text) == (
        "3 bands of the proteins in the 61 genomes of Plasmodium, each with a floor "
        "on the proteins in the 15 genomes of Toxoplasma gondii: exactly 1 with at "
        "least 3; exactly 2 with at least 4; exactly 4 with at least 6"
    )


def test_an_offset_that_changes_lists_the_bands_and_not_a_range() -> None:
    text = " OR ".join(
        f"{'+'.join(_PLASMODIUM)}={n} AND {'+'.join(_TOXOPLASMA)}>={floor}"
        for n, floor in ((1, 2), (2, 5), (3, 6))
    )

    assert "exactly 1 with at least 2; exactly 2 with at least 5;" in _read(text)


def test_a_strict_floor_reads_as_the_next_count() -> None:
    plasmodium, toxoplasma = "+".join(_PLASMODIUM), "+".join(_TOXOPLASMA)
    text = f"{plasmodium}=1 AND {toxoplasma}>2 OR {plasmodium}=3 AND {toxoplasma}>5"

    assert _read(text).endswith(
        ": exactly 1 with at least 3; exactly 3 with at least 6"
    )


def test_the_floor_may_be_written_first() -> None:
    written = " OR ".join(f"tgon>={n + 1} AND pfal={n}" for n in range(112))

    assert _read(written) == _read(_MORE_IN_ONE_GENOME)


def test_a_band_wider_than_one_count_is_no_constant_lead() -> None:
    plasmodium, toxoplasma = "+".join(_PLASMODIUM), "+".join(_TOXOPLASMA)
    text = (
        f"{plasmodium}=1 AND {toxoplasma}>=2 OR "
        f"{plasmodium}>=2 AND {plasmodium}<=3 AND {toxoplasma}>=3"
    )

    assert _read(text).endswith(": exactly 1 with at least 2; 2 to 3 with at least 3")


def test_a_floor_at_the_count_itself_lists_the_bands_and_not_a_lead() -> None:
    text = " OR ".join(
        f"{'+'.join(_PLASMODIUM)}={n} AND {'+'.join(_TOXOPLASMA)}>={n}"
        for n in (1, 2, 3)
    )

    assert "exactly 1 with at least 1; exactly 2 with at least 2;" in _read(text)


def test_counts_of_two_kinds_list_the_bands_and_not_a_lead() -> None:
    text = " OR ".join(
        f"{'+'.join(_PLASMODIUM)}={n}T AND {'+'.join(_TOXOPLASMA)}>={n + 1}"
        for n in (1, 2, 3)
    )

    assert _read(text).startswith(
        "3 bands of the genomes in the 61 genomes of Plasmodium, each with a floor on "
        "the proteins in the 15 genomes of Toxoplasma gondii: exactly 1 with at least 2"
    )


def test_a_floor_that_does_not_rise_is_no_comparison() -> None:
    [text] = _corpus_writings("orthomcl-in-3d7-missing-from-two-falciparum-strains")
    listed = ", ".join(
        node.label.removeprefix("Plasmodium falciparum ")
        for node in _TREE.nodes()
        if node.code in _FALCIPARUM and node.code != "pfal"
    )
    these = f"these 19 (19 of the 20 genomes of Plasmodium falciparum: {listed})"

    assert _read(text) == (
        f"(at least 1 genome of Plasmodium falciparum 3D7 and none of {these}) or "
        f"(at least 1 genome of Plasmodium falciparum 3D7 and 1 to 17 of {these})"
    )


def test_two_sides_that_are_both_bounded_are_no_comparison() -> None:
    plasmodium, toxoplasma = "+".join(_PLASMODIUM), "+".join(_TOXOPLASMA)
    text = f"{plasmodium}=1 AND {toxoplasma}=2 OR {plasmodium}=2 AND {toxoplasma}=3"

    assert _read(text) == (
        "(exactly 1 protein in the 61 genomes of Plasmodium and exactly 2 proteins in "
        "the 15 genomes of Toxoplasma gondii) or (exactly 2 proteins in the 61 genomes "
        "of Plasmodium and exactly 3 proteins in the 15 genomes of Toxoplasma gondii)"
    )


def test_terms_over_other_sets_are_no_comparison() -> None:
    plasmodium, toxoplasma = "+".join(_PLASMODIUM), "+".join(_TOXOPLASMA)
    text = f"{plasmodium}=1 AND {toxoplasma}>=2 OR {plasmodium}=2 AND tgon>=3"

    assert " with at least " not in _read(text)
    assert _read(text).startswith("(exactly 1 protein in the 61 genomes of Plasmodium")


def test_a_share_of_a_genus_states_the_share() -> None:
    [text] = _corpus_writings("orthomcl-most-plasmodium-genomes-no-toxoplasma")

    assert _read(text) == (
        "at least 55 of the 61 genomes of Plasmodium and none of the 15 genomes of "
        "Toxoplasma gondii"
    )


def test_presence_in_a_genus_reads_as_one_genome_of_it() -> None:
    [text] = _corpus_writings("orthomcl-plasmodium-and-cryptosporidium-not-toxoplasma")

    assert _read(text) == (
        "at least 1 of the 61 genomes of Plasmodium and at least 1 of the 18 genomes "
        "of Cryptosporidium and none of the 15 genomes of Toxoplasma gondii"
    )
    assert (_holds(text, {"padl": 1, "cand": 1}), _holds(text, {"padl": 1})) == (
        True,
        False,
    )


def test_every_genome_of_a_genus_reads_as_all_of_it() -> None:
    [text] = _corpus_writings("orthomcl-one-protein-in-each-cryptosporidium-genome")

    assert _read(text) == (
        "all of the 18 genomes of Cryptosporidium and exactly 18 proteins in the 18 "
        "genomes of Cryptosporidium"
    )
    every = dict.fromkeys(_CRYPTOSPORIDIUM, 1)
    assert (
        _holds(text, every),
        _holds(text, {k: v for k, v in every.items() if k != "cand"}),
    ) == (True, False)


def test_a_clade_of_the_tree_reads_by_its_own_name() -> None:
    [text] = _corpus_writings("orthomcl-one-protein-in-every-apicomplexan-genome")

    assert _read(text) == (
        "all of the 139 genomes of Apicomplexa and exactly 139 proteins in the 139 "
        "genomes of Apicomplexa"
    )


def test_absence_and_presence_of_whole_groups_read_by_their_names() -> None:
    [text] = _corpus_writings("orthomcl-toxoplasma-groups-absent-from-cryptosporidium")

    assert _read(text) == (
        "at least 1 of the 15 genomes of Toxoplasma gondii and none of the 18 genomes "
        "of Cryptosporidium"
    )


_SHARES_BY_SPECIES = (
    "padl>=1T AND pber>=1T AND pbil>=1T AND pblg>=1T AND pbbi>=1T AND "
    "pcha+pccb>=1T AND pcoa>=1T AND pcyn+pcym>=1T AND "
    "pfal+pfag+pfsg+pfac+pfad+pfga+pfgb+pfgn+pfhb+pfai+pfke+pfkh+pfkt+pfml+pfnc+pfng+pfnf+pfsd+pfsn+pftg>=10T "
    "AND pfra>=1T AND pgab+pgas>=1T AND pgal>=1T AND pinu>=1T AND "
    "pkah+pkno+pknp>=2T AND pmal>=1T AND pova+powp>=1T AND ppra>=1T AND "
    "prei+preg>=1T AND prel>=1T AND pvbd+pvce+pvld+pvcr+pvpc+pvvc+pvin>=4T AND "
    "pvlk>=1T AND pvip+pvpv+pvpw+pviv>=2T AND pyoe+pyxn+pyyx+pyoy>=2T AND "
    "tgar+tgca+tgco+tgfo+tggd+tggt+tgma+tgon+tgop+tgee+tgru+tgta+tgtg+tgva+tgve=0T"
)


def test_a_species_reading_with_shares_keeps_each_species_own_share() -> None:
    reading = _read(_SHARES_BY_SPECIES)

    assert reading.startswith(
        "at least 1 genome in each of 18 species (23 genomes: Plasmodium adleri, "
    )
    assert reading.endswith(
        "Plasmodium vivax-like) and at least 10 of the 20 genomes of Plasmodium "
        "falciparum and at least 2 genomes in each of 3 species (11 genomes: Plasmodium "
        "knowlesi, Plasmodium vivax, Plasmodium yoelii) and at least 4 of the 7 genomes "
        "of Plasmodium vinckei and none of the 15 genomes of Toxoplasma gondii"
    )


def test_one_genome_per_species_reads_as_one_genome_per_species() -> None:
    [text] = _corpus_writings("orthomcl-all-plasmodium-every-species-reading")

    assert _read(text) == (
        "at least 1 genome in each of the 23 species of Plasmodium (61 genomes) "
        "and none of the 15 genomes of Toxoplasma gondii"
    )


@pytest.mark.parametrize(
    "writing", ["tgon>=5 AND pfal=1", "MAMM=0T AND tgon>=1T", "MAMM=0T"]
)
def test_a_small_expression_keeps_the_described_reading(writing: str) -> None:
    assert _read(writing) == PhyleticExpression.parse(writing).describe(_TREE)


def test_a_list_that_misses_one_genome_is_listed_and_not_folded() -> None:
    held = [code for code in _TOXOPLASMA if code != "tgve"]
    reading = _read(f"{'+'.join(held)}>=1T AND {'+'.join(_CRYPTOSPORIDIUM)}=0T")

    assert reading.startswith(
        "at least 1 of these 14 (14 of the 15 genomes of Toxoplasma gondii: ARI, CAST, "
    )
    assert ("VEG" in reading, "1 of the 15 genomes of Toxoplasma" in reading) == (
        False,
        False,
    )


def test_presence_short_of_a_species_stays_out_of_the_species_fold() -> None:
    text = (
        f"{'+'.join(_TOXOPLASMA[:-1])}>=1T AND {'+'.join(_CRYPTOSPORIDIUM[:1])}>=1T "
        f"AND {'+'.join(_PLASMODIUM)}>=1T"
    )

    assert "in each of" not in _read(text)


def test_genomes_short_of_a_genus_are_not_read_as_the_genus() -> None:
    species = _TREE.species_groups(_PLASMODIUM)[:-1]
    text = " AND ".join(f"{'+'.join(one.genomes)}>=1T" for one in species)

    reading = _read(text)

    assert reading.startswith("at least 1 genome in each of 22 species (57 genomes: ")
    assert "species of Plasmodium" not in reading


@pytest.mark.parametrize("path", sorted(CORPUS_DIR.glob("orthomcl-*.json")))
def test_every_corpus_writing_reads_short_and_names_no_code(path: Path) -> None:
    case = EvalCase.model_validate_json(path.read_text())

    for writing in case.expected.expressions.get(_PHYLETIC, []):
        reading = _read(writing)
        codes = PhyleticExpression.parse(writing).codes()
        assert len(reading) <= READING_LIMIT
        assert [code for code in codes if f" {code} " in f" {reading} "] == []
        assert "characters" not in reading
