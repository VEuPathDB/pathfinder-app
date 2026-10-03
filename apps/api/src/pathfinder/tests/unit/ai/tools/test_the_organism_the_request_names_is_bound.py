"""A bind that holds a sibling or an ancestor of an organism entry the request
names, in place of that entry, is refused; another lineage is never refused."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import WDKTreeBoxVocabNode
from veupathdb.wdk import WDKParameter, WDKSearch
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall
from pathfinder.ai.tools.standalone._frame_stated import refuse_what_the_words_decide
from pathfinder.tests._support.recorded_searches import suite_search

_SIGNAL = "GenesWithSignalPeptide"
_UKMEL1 = "Cryptosporidium meleagridis UKMEL1"
_TU1867 = "Cryptosporidium meleagridis TU1867"
_REQUEST = f"{_UKMEL1} genes with a signal peptide expressed in oocysts."


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


def _bind(
    definition: WDKSearch,
    message: str,
    organisms: list[str],
    search_name: str = _SIGNAL,
) -> list[str]:
    """The organisms the call binds; a refusal raises instead."""
    call = CriterionCall(
        criterion_id="c_signal",
        search_name=search_name,
        text="genes with a signal peptide",
        params={"organism": organisms},
    )
    infos = format_param_info_typed(definition.parameters or [])
    refuse_what_the_words_decide(definition, call, infos, [message])
    return organisms


def test_a_sibling_of_the_named_entry_is_refused() -> None:
    with pytest.raises(ModelRetry) as refused:
        _bind(_CRYPTO, _REQUEST, [_TU1867])

    assert refused.value.message == (
        f"Organism on {_SIGNAL} holds ['{_TU1867}'], and the request names "
        f"'{_UKMEL1}', an entry of this vocabulary. Bind the entry the request "
        "names, or ask the researcher which one they mean."
    )


def test_the_named_entry_binds() -> None:
    assert _bind(_CRYPTO, _REQUEST, [_UKMEL1]) == [_UKMEL1]


def test_a_named_genus_binds_its_species() -> None:
    species = [
        "Plasmodium falciparum 3D7",
        "Plasmodium vivax P01",
        "Plasmodium berghei ANKA",
    ]

    assert _bind(_PLASMO, "Plasmodium genes with a signal peptide.", species) == species


def test_a_message_that_names_no_entry_binds_any_strain() -> None:
    assert _bind(_CRYPTO, "meleagridis genes with a signal peptide.", [_TU1867]) == [
        _TU1867
    ]


def test_a_second_organism_the_request_names_binds_alone() -> None:
    assert _bind(
        _PLASMO,
        "Plasmodium falciparum 3D7 genes with orthologs in Plasmodium vivax P01.",
        ["Plasmodium vivax P01"],
    ) == ["Plasmodium vivax P01"]


def test_a_genus_above_the_named_strain_is_refused() -> None:
    with pytest.raises(ModelRetry) as refused:
        _bind(
            _PLASMO,
            "Plasmodium falciparum 3D7 genes with a signal peptide.",
            ["Plasmodium"],
        )

    assert refused.value.message == (
        f"Organism on {_SIGNAL} holds ['Plasmodium'], and the request names "
        "'Plasmodium falciparum 3D7', an entry of this vocabulary. Bind the entry "
        "the request names, or ask the researcher which one they mean."
    )


def test_an_organism_of_another_criterion_leaves_this_bind_alone() -> None:
    hostdb = _flat_search("GenesByGoTerm", "Homo sapiens REF", "Mus musculus C57BL/6J")
    message = (
        "Homo sapiens genes on chromosome X with the GO term 'immune response' "
        "that have an ortholog in Mus musculus C57BL/6J."
    )

    assert _bind(hostdb, message, ["Homo sapiens REF"], "GenesByGoTerm") == [
        "Homo sapiens REF"
    ]


def test_another_lineage_beside_a_named_entry_binds() -> None:
    fungi = _flat_search(
        _SIGNAL, "Candida albicans SC5314", "Saccharomyces cerevisiae S288c"
    )
    message = (
        "Candida albicans SC5314 genes with a signal peptide and no ortholog in "
        "Saccharomyces cerevisiae S288c."
    )

    assert _bind(fungi, message, ["Candida albicans SC5314"]) == [
        "Candida albicans SC5314"
    ]


def test_a_strain_of_the_same_species_with_no_parent_is_refused() -> None:
    flat = _flat_search(_SIGNAL, _UKMEL1, _TU1867)

    with pytest.raises(ModelRetry) as refused:
        _bind(flat, _REQUEST, [_TU1867])

    assert refused.value.message == (
        f"Organism on {_SIGNAL} holds ['{_TU1867}'], and the request names "
        f"'{_UKMEL1}', an entry of this vocabulary. Bind the entry the request "
        "names, or ask the researcher which one they mean."
    )
