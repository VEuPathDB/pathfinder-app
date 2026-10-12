"""An entry of the organism tree stands for the organisms under it, so a search
scoped to a taxon meets a search or a study scoped to one of its organisms."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode

from pathfinder.domain.strategy.validate import (
    cross_organism_refusal,
    first_cross_organism_refusal,
    validate_strategy,
)

from ._builders import combine

_PF = "Plasmodium falciparum 3D7"
_PK = "Plasmodium knowlesi strain H"
_TG = "Toxoplasma gondii ME49"
_STRAIN = "Aspergillus nidulans FGSC A4"
_SPECIES = "Aspergillus nidulans"
_MARKED = {"GenesByGoTerm": "organism"}
_TAXA = {
    "Apicomplexa": frozenset({_PF, _PK, _TG}),
    "Plasmodium": frozenset({_PF, _PK}),
    _SPECIES: frozenset({_STRAIN}),
}


def _annotated(step_id: str, organism: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name="GenesByGoTerm",
        parameters={"organism": MultiPickValue(values=[organism])},
    )


def _study(step_id: str) -> StrategyStepNode:
    return StrategyStepNode(id=step_id, search_name="GenesByEdaSubset")


def _refused(primary: str, secondary: str) -> str:
    return (
        f"Cannot INTERSECT steps with different organism scopes ({primary} vs "
        f"{secondary}). Gene IDs from different organisms never match, so this "
        f"always returns 0 results. Scope every seed to one organism: {primary} "
        f"or {secondary}."
    )


def test_a_taxon_meets_an_organism_under_it() -> None:
    root = combine("c", _annotated("a", "Apicomplexa"), _annotated("b", _PK))

    assert (
        cross_organism_refusal(root, root, _MARKED, {}),
        cross_organism_refusal(root, root, _MARKED, {}, taxa=_TAXA),
    ) == (_refused("Apicomplexa", _PK), None)


def test_a_species_entry_meets_its_own_strain_in_either_order() -> None:
    one = combine("c", _annotated("a", _STRAIN), _annotated("b", _SPECIES))
    other = combine("c", _annotated("a", _SPECIES), _annotated("b", _STRAIN))

    assert [
        cross_organism_refusal(root, root, _MARKED, {}, taxa=_TAXA)
        for root in (one, other)
    ] == [None, None]


def test_a_taxon_meets_a_study_on_an_organism_under_it() -> None:
    root = combine("c", _annotated("a", "Apicomplexa"), _study("study"))
    datasets = {"study": frozenset({_PK})}

    by_name = (
        f"Cannot INTERSECT steps with different organism scopes (Apicomplexa vs "
        f"{_PK}). Gene IDs from different organisms never match, so this always "
        f"returns 0 results. The GenesByEdaSubset search runs on an experiment of "
        f"{_PK}, and no parameter changes that organism. Map that side to "
        f"Apicomplexa with a GenesByOrthologs transform."
    )

    assert (
        first_cross_organism_refusal(root, _MARKED, datasets),
        first_cross_organism_refusal(root, _MARKED, datasets, taxa=_TAXA),
    ) == (by_name, None)


def test_two_taxa_that_share_an_organism_meet() -> None:
    root = combine("c", _annotated("a", "Apicomplexa"), _annotated("b", "Plasmodium"))

    assert (
        cross_organism_refusal(root, root, _MARKED, {}),
        cross_organism_refusal(root, root, _MARKED, {}, taxa=_TAXA),
    ) == (_refused("Apicomplexa", "Plasmodium"), None)


def test_a_taxon_does_not_meet_an_organism_outside_it() -> None:
    root = combine("c", _annotated("a", "Plasmodium"), _annotated("b", _TG))

    assert cross_organism_refusal(root, root, _MARKED, {}, taxa=_TAXA) == _refused(
        "Plasmodium", _TG
    )


def test_only_an_intersect_of_two_scopes_is_refused() -> None:
    taxon, outside = _annotated("a", "Plasmodium"), _annotated("b", _TG)

    assert [
        first_cross_organism_refusal(
            combine("c", taxon, outside, operator), _MARKED, {}, taxa=_TAXA
        )
        for operator in (CombineOp.UNION, CombineOp.INTERSECT)
    ] == [None, _refused("Plasmodium", _TG)]


def test_the_validator_reads_the_taxa() -> None:
    root = combine("c", _annotated("a", "Apicomplexa"), _annotated("b", _PK))

    by_name = validate_strategy(root, "transcript", _MARKED)
    by_organism = validate_strategy(root, "transcript", _MARKED, taxa=_TAXA)

    assert (
        [issue.message for issue in by_name.errors],
        by_organism.valid,
        by_organism.errors,
    ) == ([_refused("Apicomplexa", _PK)], True, [])
