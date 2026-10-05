"""A bind that holds a sibling or an ancestor of an organism entry the request
names, in place of that entry, is refused; another lineage is never refused.
The request names the organisms its live requirements state."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import WDKTreeBoxVocabNode
from veupathdb.wdk import WDKParameter, WDKSearch
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall
from pathfinder.ai.tools.standalone._frame_stated import refuse_what_the_words_decide
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.tests._support.recorded_searches import suite_search

_SIGNAL = "GenesWithSignalPeptide"
_UKMEL1 = "Cryptosporidium meleagridis UKMEL1"
_TU1867 = "Cryptosporidium meleagridis TU1867"


def _node(term: str, *children: dict[str, object]) -> dict[str, object]:
    return {"data": {"term": term, "display": term}, "children": list(children)}


_CRYPTO_ORGANISM: WDKParameter = TypeAdapter(WDKParameter).validate_python(
    {
        "name": "organism",
        "displayName": "Organism",
        "type": "multi-pick-vocabulary",
        "displayType": "treeBox",
        "minSelectedCount": 1,
        "maxSelectedCount": -1,
        "isVisible": True,
        "isReadOnly": False,
        "allowEmptyValue": False,
        "initialDisplayValue": "[]",
        "dependentParams": [],
        "group": "empty",
        "properties": {"organismProperties": []},
        "vocabulary": _node(
            "@@fake@@",
            _node(
                "Cryptosporidium",
                _node(_UKMEL1),
                _node(_TU1867),
                _node("Cryptosporidium parvum Iowa II"),
            ),
        ),
    }
)
_CRYPTO = WDKSearch(url_segment=_SIGNAL, parameters=[_CRYPTO_ORGANISM])
_PLASMO = suite_search("search_genes_with_signal_peptide")


def _flat_search(search_name: str, *organisms: str) -> WDKSearch:
    """A search whose organism entries sit under the tree's root, with no parent."""
    root = TypeAdapter(WDKTreeBoxVocabNode).validate_python(
        _node("@@fake@@", *(_node(organism) for organism in organisms))
    )
    return WDKSearch(
        url_segment=search_name,
        parameters=[_CRYPTO_ORGANISM.model_copy(update={"vocabulary": root})],
    )


def _organism(requested: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.ORGANISM, requested_value=requested, label="organism"
    )


def _bind_under(
    definition: WDKSearch,
    requirements: list[Constraint],
    organisms: list[str],
    search_name: str = _SIGNAL,
) -> list[str]:
    """The organisms the call binds under the live requirements; a refusal
    raises instead."""
    call = CriterionCall(
        criterion_id="c_signal",
        search_name=search_name,
        text="genes with a signal peptide",
        params={"organism": organisms},
    )
    infos = format_param_info_typed(definition.parameters or [])
    refuse_what_the_words_decide(
        definition, call, infos, AgentToolState(stated_requirements=requirements)
    )
    return organisms


def _bind(
    definition: WDKSearch,
    named: list[str],
    organisms: list[str],
    search_name: str = _SIGNAL,
) -> list[str]:
    """The organisms the call binds when the live requirements name ``named``."""
    return _bind_under(
        definition, [_organism(n) for n in named], organisms, search_name
    )


def test_a_sibling_of_the_named_entry_is_refused() -> None:
    with pytest.raises(ModelRetry) as refused:
        _bind(_CRYPTO, [_UKMEL1], [_TU1867])

    assert refused.value.message == (
        f"Organism on {_SIGNAL} binds ['{_TU1867}'], and the request names "
        f"'{_UKMEL1}', an entry of this vocabulary. Bind the entry the request "
        "names, or ask the researcher which one they mean."
    )


def test_the_named_entry_binds() -> None:
    assert _bind(_CRYPTO, [_UKMEL1], [_UKMEL1]) == [_UKMEL1]


def test_a_named_genus_binds_its_species() -> None:
    assert _bind(_CRYPTO, ["Cryptosporidium"], [_UKMEL1]) == [_UKMEL1]


def test_a_request_with_no_organism_requirement_binds_any_strain() -> None:
    assert _bind(_CRYPTO, [], [_TU1867]) == [_TU1867]


def test_a_second_organism_the_request_names_binds_alone() -> None:
    assert _bind(
        _PLASMO,
        ["Plasmodium falciparum 3D7", "Plasmodium vivax P01"],
        ["Plasmodium vivax P01"],
    ) == ["Plasmodium vivax P01"]


def test_a_genus_above_the_named_strain_is_refused() -> None:
    with pytest.raises(ModelRetry) as refused:
        _bind(_PLASMO, ["Plasmodium falciparum 3D7"], ["Plasmodium"])

    assert refused.value.message == (
        f"Organism on {_SIGNAL} binds ['Plasmodium'], and the request names "
        "'Plasmodium falciparum 3D7', an entry of this vocabulary. Bind the entry "
        "the request names, or ask the researcher which one they mean."
    )


def test_an_organism_of_another_criterion_leaves_this_bind_alone() -> None:
    hostdb = _flat_search("GenesByGoTerm", "Homo sapiens REF", "Mus musculus C57BL/6J")

    assert _bind(
        hostdb,
        ["Homo sapiens REF", "Mus musculus C57BL/6J"],
        ["Mus musculus C57BL/6J"],
        search_name="GenesByGoTerm",
    ) == ["Mus musculus C57BL/6J"]


def test_another_lineage_beside_a_named_entry_binds() -> None:
    fungi = _flat_search(
        _SIGNAL, "Candida albicans SC5314", "Saccharomyces cerevisiae S288c"
    )

    assert _bind(
        fungi,
        ["Candida albicans SC5314", "Saccharomyces cerevisiae S288c"],
        ["Candida albicans SC5314"],
    ) == ["Candida albicans SC5314"]


def test_a_strain_of_the_same_species_with_no_parent_is_refused() -> None:
    flat = _flat_search(_SIGNAL, _UKMEL1, _TU1867)

    with pytest.raises(ModelRetry):
        _bind(flat, [_UKMEL1], [_TU1867])


def test_a_replaced_organism_frees_the_strain_that_replaced_it() -> None:
    """Once a later message replaces the strain, only the new one is a live
    requirement, and the new one binds."""
    assert _bind(_CRYPTO, [_TU1867], [_TU1867]) == [_TU1867]


def test_the_replaced_strain_is_refused_in_place_of_the_new_one() -> None:
    with pytest.raises(ModelRetry) as refused:
        _bind(_CRYPTO, [_TU1867], [_UKMEL1])

    assert f"the request names '{_TU1867}'" in refused.value.message


def test_a_requirement_of_another_kind_names_no_organism() -> None:
    other = Constraint(
        kind=ConstraintKind.OTHER, requested_value=_UKMEL1, label="other"
    )

    assert _bind_under(_CRYPTO, [other], [_TU1867]) == [_TU1867]


def test_a_bind_of_a_named_genus_substitutes_for_no_species_it_holds() -> None:
    """The species an orthology profile names leave the genus the request
    asks for free to bind."""
    assert _bind(
        _PLASMO,
        ["Plasmodium", "P. berghei", "P. knowlesi", "Toxoplasma gondii"],
        ["Plasmodium"],
    ) == ["Plasmodium"]


def test_a_bind_of_a_named_strain_substitutes_for_no_sibling_strain() -> None:
    assert _bind(
        _PLASMO,
        ["Plasmodium falciparum 3D7", "Plasmodium falciparum HB3"],
        ["Plasmodium falciparum 3D7"],
    ) == ["Plasmodium falciparum 3D7"]
