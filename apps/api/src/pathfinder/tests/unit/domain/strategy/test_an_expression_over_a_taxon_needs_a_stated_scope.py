from __future__ import annotations

import pytest
from veupathdb.domain.parameters import PhyleticExpression, PhyleticTree, TaxonEntry

from pathfinder.domain.strategy.named_groups import (
    GroupScope,
    NamedGroup,
    merged_scopes,
    scoped_taxa,
    taxa_to_scope,
    unscoped_taxa,
    whole_taxa,
)
from pathfinder.tests._support.ortho_taxonomy import (
    labelled_genomes,
    recorded_ortho_taxonomy,
)

TREE = recorded_ortho_taxonomy()
PLAS = labelled_genomes(TREE, "Plasmodium ")
TOXO = labelled_genomes(TREE, "Toxoplasma ")
FALC = labelled_genomes(TREE, "Plasmodium falciparum ")
WHOLE = GroupScope(taxon="Plasmodium", scope="whole")


def _parsed(text: str) -> list[PhyleticExpression]:
    return [PhyleticExpression.parse(text)]


def _taxa(text: str) -> list[tuple[str, frozenset[str]]]:
    return [(group.name, group.genomes) for group in taxa_to_scope(_parsed(text), TREE)]


TWO = "pfal>=1T AND pviv>=1T"
VIVAX = labelled_genomes(TREE, "Plasmodium vivax ")


def _unscoped(text: str, *stated: GroupScope) -> list[str]:
    expressions = _parsed(text)
    scoped = scoped_taxa({}, stated, expressions, TREE)
    return [group.taxon for group in unscoped_taxa(expressions, TREE, scoped)]


def _wholes(*stated: GroupScope) -> list[NamedGroup]:
    return [taxon.required for taxon in whole_taxa(scoped_taxa({}, stated, [], TREE))]


def test_units_over_two_species_of_a_genus_need_the_genus_scoped() -> None:
    assert _taxa("pfal>=1T AND pviv>=1T") == [("Plasmodium", frozenset(PLAS))]


def test_units_over_two_genomes_of_one_species_need_the_species_scoped() -> None:
    assert _taxa(f"{FALC[0]}+{FALC[1]}>=1T") == [
        ("Plasmodium falciparum", frozenset(FALC))
    ]


@pytest.mark.parametrize(
    "text", [f"{'+'.join(TOXO)}=0T", f"pfal>=1T AND {'+'.join(TOXO)}=0T"]
)
def test_units_that_only_write_absence_need_no_scope(text: str) -> None:
    assert _taxa(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "pfal>=1T",
        "pfal>=1T AND tgon>=1T AND hsap=0T",
        "HAEM>=1T",
        "OBAC>=1T AND OMET>=1T",
    ],
)
def test_one_genome_per_genus_or_a_clade_code_needs_no_scope(text: str) -> None:
    assert _taxa(text) == []


@pytest.mark.parametrize(
    "scope",
    [
        WHOLE,
        GroupScope(taxon="plasmodium", scope="named"),
        GroupScope(taxon="Haemosporida", scope="whole"),
    ],
)
def test_a_scope_over_the_taxon_or_a_wider_one_scopes_it(scope: GroupScope) -> None:
    assert _unscoped(TWO, scope) == []


@pytest.mark.parametrize(
    "scope",
    [
        GroupScope(taxon="Plasmodium falciparum", scope="whole"),
        GroupScope(taxon="Plasmodia of all kinds", scope="whole"),
    ],
)
def test_a_narrower_or_unknown_taxon_leaves_the_taxon_unscoped(
    scope: GroupScope,
) -> None:
    assert _unscoped(TWO, scope) == ["Plasmodium"]


def test_a_whole_scope_is_its_taxon_without_the_excepted_genomes() -> None:
    scope = GroupScope(taxon="Plasmodium", scope="whole", except_codes=["pber"])

    assert [(group.name, group.genomes) for group in _wholes(scope)] == [
        ("Plasmodium except pber", frozenset(PLAS) - {"pber"})
    ]


@pytest.mark.parametrize(
    "scope",
    [
        GroupScope(taxon="Plasmodium", scope="named"),
        GroupScope(taxon="Plasmodia of all kinds", scope="whole"),
        GroupScope(taxon="Plasmodium", scope="whole", except_codes=PLAS),
    ],
)
def test_a_named_unknown_or_emptied_scope_holds_no_group(scope: GroupScope) -> None:
    assert _wholes(scope) == []


def test_a_stated_scope_replaces_the_held_scope_of_its_taxon() -> None:
    named = GroupScope(taxon="plasmodium", scope="named")

    assert merged_scopes({"plasmodium": WHOLE}, [named]) == {"plasmodium": named}


def test_the_genomes_no_unit_names_are_left_out() -> None:
    (group,) = _wholes(WHOLE)
    kept = [code for code in PLAS if code not in {"pccb", "pcym"}]
    partial = PhyleticExpression.parse(
        f"{' AND '.join(f'{code}>=1T' for code in kept)} AND {'+'.join(TOXO)}=0T"
    )

    assert group.left_out([partial], TREE) == ["pccb", "pcym"]


def test_a_list_or_a_clade_over_the_group_leaves_nothing_out() -> None:
    (group,) = _wholes(WHOLE)

    assert group.left_out([PhyleticExpression.parse("HAEM>=1T")], TREE) == []
    assert (
        group.left_out([PhyleticExpression.parse(f"{'+'.join(PLAS)}>=50T")], TREE) == []
    )


def test_an_expression_over_none_of_the_group_leaves_nothing_out() -> None:
    (group,) = _wholes(WHOLE)

    assert group.left_out([PhyleticExpression.parse("tgon>=1T")], TREE) == []


def test_two_expressions_together_cover_the_group() -> None:
    (group,) = _wholes(WHOLE)
    half = len(PLAS) // 2
    first = PhyleticExpression.parse(f"{'+'.join(PLAS[:half])}>=1T")
    second = PhyleticExpression.parse(f"{'+'.join(PLAS[half:])}>=1T")

    assert group.left_out([first, second], TREE) == []
    assert group.left_out([first], TREE) == PLAS[half:]


def test_a_species_inside_a_genus_that_needs_a_scope_is_not_asked_apart() -> None:
    assert _taxa(f"{'+'.join(FALC)}>=10T AND pviv>=1T") == [
        ("Plasmodium", frozenset(PLAS))
    ]


@pytest.mark.parametrize("taxon", ["HAEM", "Haemosporida", "Plasmodium"])
def test_a_clade_code_or_a_full_name_scopes_the_taxon(taxon: str) -> None:
    scope = GroupScope(taxon=taxon, scope="named")

    assert _unscoped(TWO, scope) == []


def test_a_clade_scope_holds_the_clade_s_genomes() -> None:
    scope = GroupScope(taxon="HAEM", scope="whole")

    assert [(group.name, group.taxon, group.genomes) for group in _wholes(scope)] == [
        ("Haemosporida", "HAEM", frozenset(TREE.genomes_under(["HAEM"])))
    ]


@pytest.mark.parametrize("taxon", ["P. vivax", "haem", "pviv"])
def test_a_taxon_the_taxonomy_does_not_name_scopes_nothing(taxon: str) -> None:
    scope = GroupScope(taxon=taxon, scope="named")

    assert _unscoped(TWO, scope) == ["Plasmodium"]


def _entry(code: str, label: str, parent: str | None, *, clade: bool) -> TaxonEntry:
    return TaxonEntry(id=code, parent_id=parent, code=code, label=label, clade=clade)


def test_a_name_two_nodes_carry_resolves_to_neither() -> None:
    tree = PhyleticTree.from_taxa(
        [
            _entry("TOXO", "Toxoplasma", None, clade=True),
            _entry("tgon", "Toxoplasma gondii ME49", "TOXO", clade=False),
            _entry("ncan", "Neospora caninum Liverpool", "TOXO", clade=False),
        ]
    )
    by_name = scoped_taxa({}, [GroupScope(taxon="Toxoplasma", scope="whole")], [], tree)
    by_code = scoped_taxa({}, [GroupScope(taxon="TOXO", scope="whole")], [], tree)

    assert by_name == []
    assert [taxon.group.genomes for taxon in by_code] == [frozenset({"tgon", "ncan"})]


def test_a_held_whole_scope_the_expression_does_not_span_does_not_apply() -> None:
    narrowed = _parsed(f"{'+'.join(VIVAX)}>={len(VIVAX)}T")
    scoped = scoped_taxa({"plasmodium": WHOLE}, [], narrowed, TREE)

    assert scoped == []
    assert [g.taxon for g in unscoped_taxa(narrowed, TREE, scoped)] == [
        "Plasmodium vivax"
    ]


def test_a_held_scope_the_expression_still_spans_applies_as_held() -> None:
    scoped = scoped_taxa({"plasmodium": WHOLE}, [], _parsed(TWO), TREE)

    assert [(t.group.taxon, t.scope.scope, t.held) for t in scoped] == [
        ("Plasmodium", "whole", True)
    ]


def test_a_held_species_scope_applies_to_two_of_its_genomes() -> None:
    held = {"plasmodium vivax": GroupScope(taxon="Plasmodium vivax", scope="whole")}
    scoped = scoped_taxa(held, [], _parsed(f"{VIVAX[0]}+{VIVAX[1]}>=1T"), TREE)

    assert [t.group.taxon for t in scoped] == ["Plasmodium vivax"]


def test_a_scope_stated_under_another_spelling_replaces_the_held_one() -> None:
    held = {"haem": GroupScope(taxon="HAEM", scope="whole")}
    named = GroupScope(taxon="Haemosporida", scope="named")

    assert [
        (t.scope, t.held) for t in scoped_taxa(held, [named], _parsed(TWO), TREE)
    ] == [(named, False)]


def test_the_latest_of_two_held_spellings_is_the_one_that_applies() -> None:
    held = merged_scopes(
        merged_scopes({}, [GroupScope(taxon="HAEM", scope="whole")]),
        [GroupScope(taxon="Haemosporida", scope="named")],
    )
    held = merged_scopes(held, [GroupScope(taxon="HAEM", scope="whole")])

    assert [t.scope.taxon for t in scoped_taxa(held, [], _parsed(TWO), TREE)] == [
        "HAEM"
    ]


@pytest.mark.parametrize("codes", [["P. berghei"], ["tgon"], ["pber", "HAEM"]])
def test_an_exception_that_is_no_genome_of_the_taxon_is_stray(
    codes: list[str],
) -> None:
    scope = GroupScope(taxon="Plasmodium", scope="whole", except_codes=codes)

    assert [t.stray_codes for t in scoped_taxa({}, [scope], [], TREE)] == [
        [code for code in codes if code != "pber"]
    ]
