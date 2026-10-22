"""Two writings of one phyletic expression grade equal, and two meanings do not."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import PhyleticExpression, PhyleticTree, TaxonEntry
from veupathdb.errors import ValidationError

from pathfinder.evals.expressions import Meaning, meaning
from pathfinder.tests.unit.evals._phyletic import clade_codes, clade_tree

TREE = clade_tree({"APIC": 139, "PLAS": 61, "TOXO": 15})


def _codes(clade: str) -> list[str]:
    return clade_codes(clade, len(TREE.genomes_under([clade])))


def _site_reading(text: str) -> PhyleticExpression:
    return PhyleticExpression.parse(text).site_reading()


def _same(a: str, b: str) -> bool:
    return meaning(_site_reading(a), TREE) == meaning(_site_reading(b), TREE)


def test_unit_order_does_not_change_the_meaning() -> None:
    assert _same("APIC=139T AND APIC=139", "APIC=139 AND APIC=139T")


def test_a_clade_is_its_genome_list() -> None:
    assert _same("TOXO=0T", f"{'+'.join(_codes('TOXO'))}=0T")


def test_absence_and_presence_read_alike_with_or_without_t() -> None:
    assert _same("TOXO=0T", "TOXO=0")
    assert _same(f"{_codes('TOXO')[0]}>=1T", f"{_codes('TOXO')[0]}>=1")


def test_a_zero_bound_written_below_is_not_absence() -> None:
    assert not _same("TOXO=0T", "TOXO<=0T")


def test_two_writings_of_one_upper_bound_grade_equal() -> None:
    assert _same("TOXO<1T", "TOXO<=0T")


def test_single_copy_over_a_list_is_one_protein_per_genome() -> None:
    assert _same(
        "TOXO=15T AND TOXO=15", " AND ".join(f"{code}=1" for code in _codes("TOXO"))
    )
    assert not _same(
        "TOXO=15T AND TOXO=15", " AND ".join(f"{code}>=1" for code in _codes("TOXO"))
    )


def test_strict_bounds_are_their_inclusive_twins() -> None:
    assert _same("PLAS>122 AND PLAS<183", "PLAS>=123 AND PLAS<=182")


def test_bands_compare_as_a_set() -> None:
    assert _same(
        "(PLAS>=122 AND PLAS<183 AND TOXO>=60) OR (PLAS>=183 AND PLAS<244 AND TOXO>=90)",
        "(TOXO>=90 AND PLAS<244 AND PLAS>=183) OR (PLAS<183 AND TOXO>=60 AND PLAS>=122)",
    )


def test_different_counts_are_different_meanings() -> None:
    assert not _same("PLAS=61T", "PLAS>=55T")
    assert not _same("TOXO>=8T", "TOXO>=7T")


def test_and_binds_before_or_without_parentheses() -> None:
    plas = _codes("PLAS")[0]
    assert _same(
        f"{plas}>=1T AND TOXO=0T OR {plas}>=1T AND TOXO<=13T",
        f"({plas}>=1T AND TOXO<=13T) OR ({plas}>=1T AND TOXO=0T)",
    )


def test_parentheses_are_read_as_the_site_drops_them() -> None:
    plas = _codes("PLAS")[0]
    grouped = f"{plas}>=1T AND (TOXO<=13T OR TOXO=0T)"

    assert _same(grouped, f"({plas}>=1T AND TOXO<=13T) OR TOXO=0T")
    assert not _same(grouped, f"{plas}>=1T AND TOXO=0T OR {plas}>=1T AND TOXO<=13T")


def test_a_writing_outside_the_grammar_is_refused() -> None:
    with pytest.raises(ValidationError):
        _site_reading("TOXO=0T OR")


_TWO = PhyleticTree.from_taxa(
    [
        TaxonEntry(id="1", parent_id=None, code="pfal", label="pfal", clade=False),
        TaxonEntry(id="2", parent_id=None, code="tgon", label="tgon", clade=False),
    ]
)


def _products(top: int, *, grouped: bool) -> list[str]:
    products = [f"pfal={k} AND tgon>={k + 1}" for k in range(top + 1)]
    return [f"({p})" for p in products] if grouped else products


def _two(products: list[str]) -> Meaning:
    return meaning(_site_reading(" OR ".join(products)), _TWO)


def test_a_sum_of_products_grades_alike_with_or_without_parentheses() -> None:
    grouped = _two(_products(111, grouped=True))

    assert grouped == _two(_products(111, grouped=False))
    assert grouped == _two(list(reversed(_products(111, grouped=False))))


def test_a_sum_of_products_missing_a_product_is_another_meaning() -> None:
    whole = _two(_products(111, grouped=False))

    assert whole != _two(_products(110, grouped=False))
    assert whole != _two(_products(111, grouped=False)[1:])


def _all_of(clade: str, unit: str) -> str:
    return " AND ".join(f"{code}{unit}" for code in _codes(clade))


def test_absence_one_genome_at_a_time_is_absence_over_the_list() -> None:
    assert _same(f"PLAS>=1T AND {_all_of('TOXO', '=0T')}", "PLAS>=1T AND TOXO=0T")
    assert _same(
        f"PLAS>=1T AND APIC>=1T AND {_all_of('TOXO', '=0')}",
        "PLAS>=1T AND APIC>=1T AND TOXO=0T",
    )


def test_presence_in_every_genome_one_at_a_time_is_the_list_at_its_length() -> None:
    assert _same(f"{_all_of('TOXO', '>=1T')} AND PLAS=0T", "TOXO=15T AND PLAS=0T")


def test_every_genome_of_the_parts_of_a_clade_is_every_genome_of_the_clade() -> None:
    tree = PhyleticTree.from_taxa(
        [
            TaxonEntry(id="1", parent_id=None, code="APIC", label="APIC", clade=True),
            TaxonEntry(id="2", parent_id="1", code="ACON", label="ACON", clade=True),
            TaxonEntry(id="3", parent_id="1", code="COCC", label="COCC", clade=True),
            *(
                TaxonEntry(
                    id=code, parent_id=parent, code=code, label=code, clade=False
                )
                for code, parent in [
                    ("pfal", "2"),
                    ("pviv", "2"),
                    ("tgon", "3"),
                    ("cpar", "3"),
                    ("gnip", "1"),
                ]
            ),
        ]
    )

    def read(text: str) -> Meaning:
        return meaning(_site_reading(text), tree)

    assert read("ACON=2T AND COCC=2T AND gnip=1T") == read("APIC=5T")
    assert read("ACON=2T AND COCC=2T") != read("APIC=5T")


def test_a_protein_ceiling_at_zero_is_never_absence() -> None:
    for ceiling in ("TOXO<=0", "TOXO<1", "TOXO<=0T", "TOXO<1T"):
        assert not _same("TOXO=0", ceiling)
        assert not _same("TOXO=0T", ceiling)
    assert _same("TOXO<=0", "TOXO<1")


def test_every_unit_but_zero_counts_only_groups_holding_the_list() -> None:
    assert _same("TOXO<=15T", "TOXO>=1T")
    assert _same("TOXO>=0T", "TOXO>=1T")
    assert _same("TOXO=15T AND TOXO<=15", "TOXO=15T AND TOXO=15")
    plas = _codes("PLAS")[0]
    assert _same(
        f"{plas}>=1T AND TOXO>=1T AND TOXO<=13T OR {plas}>=1T AND TOXO=0T",
        f"{plas}>=1T AND TOXO=0T OR {plas}>=1T AND TOXO<=13T",
    )
    assert not _same("TOXO=0T AND TOXO>=0", "TOXO=0T")


def test_two_floors_on_one_list_keep_the_higher() -> None:
    assert _same("TOXO>=5T AND TOXO>=2T", "TOXO>=5T")
    assert not _same("TOXO>=5T AND TOXO>=2T", "TOXO>=2T")


def test_a_genome_count_past_the_list_is_clamped_to_its_length() -> None:
    assert _same("TOXO>=10T AND TOXO<=40T", "TOXO>=10T")


def test_a_protein_count_alone_or_without_a_ceiling_is_not_single_copy() -> None:
    single = "TOXO=15T AND TOXO=15"

    assert not _same("TOXO=15", single)
    assert not _same("TOXO=15T AND TOXO>=15", single)


def test_presence_is_implied_only_by_a_unit_on_its_own_genomes_or_fewer() -> None:
    plas = _codes("PLAS")[0]

    assert not _same(f"{plas}>=1T AND PLAS>=5T", "PLAS>=5T")
    assert _same(f"PLAS>=1T AND {plas}=2", f"{plas}=2")


def test_a_ceiling_past_the_list_is_presence() -> None:
    assert _same("TOXO<=40T", "TOXO>=1T")


def test_an_empty_clade_counts_no_genome() -> None:
    tree = clade_tree({"APIC": 3, "BACI": 0})

    def read(text: str) -> Meaning:
        return meaning(_site_reading(text), tree)

    assert read("APIC+BACI=3T") == read("APIC=3T")
