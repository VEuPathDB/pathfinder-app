"""A request that names its concept only by a word every matched entry shares
binds an entry that carries that word, in any inflection; a request with a word
that tells the entries apart still refuses an entry that lacks it."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter
from pydantic_ai import ModelRetry
from veupathdb.wdk import WDKParameter, WDKSearch
from veupathdb_mcp.catalog import PhrasingMatch, VocabLookup, format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_lookups import refuse_a_pick_no_lookup_read
from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall

_SEARCH = "GenesByEcNumber"
_PARAM = "ec_number_pattern"
# The plasmodb EC entries a lookup of "kinase" matches, each labelled with a kinase.
_KINASES = [
    ("2.7.11.-", "2.7.11.- (Protein-serine/threonine kinases.)"),
    ("2.7.11.1", "2.7.11.1 (Non-specific serine/threonine protein kinase.)"),
    ("2.7.11.13", "2.7.11.13 (Protein kinase C.)"),
    ("2.7.11.17", "2.7.11.17 (Calcium/calmodulin-dependent protein kinase.)"),
    ("2.7.11.22", "2.7.11.22 (Cyclin-dependent kinase.)"),
    ("2.7.11.24", "2.7.11.24 (Mitogen-activated protein kinase.)"),
    ("2.7.11.25", "2.7.11.25 (MAP kinase kinase kinase.)"),
    ("2.7.12.2", "2.7.12.2 (Mitogen-activated protein kinase kinase.)"),
    ("2.7.1.1", "2.7.1.1 (Hexokinase.)"),
    ("2.7.1.40", "2.7.1.40 (Pyruvate kinase.)"),
    ("2.7.4.3", "2.7.4.3 (Adenylate kinase.)"),
    ("2.7.10.2", "2.7.10.2 (Non-specific protein-tyrosine kinase.)"),
]


def _typeahead() -> WDKParameter:
    return TypeAdapter(WDKParameter).validate_python(
        {
            "name": _PARAM,
            "displayName": "EC Number or Term",
            "type": "multi-pick-vocabulary",
            "displayType": "typeAhead",
            "minSelectedCount": 1,
            "maxSelectedCount": -1,
            "isVisible": True,
            "isReadOnly": False,
            "allowEmptyValue": False,
            "initialDisplayValue": "[]",
            "dependentParams": [],
            "group": "empty",
            "vocabulary": [[value, display, None] for value, display in _KINASES],
        }
    )


def _bind(picks: list[str], message: str, term: str) -> list[str]:
    """The picks the call binds after a lookup of ``term``; a refusal raises."""
    state = AgentToolState()
    state.request_messages = [message]
    state.record_lookup(
        _SEARCH,
        _PARAM,
        VocabLookup(
            terms=[term],
            matches=[
                PhrasingMatch(
                    term=term,
                    phrasing=term,
                    reach="every_word",
                    values=[value for value, _ in _KINASES],
                )
            ],
        ),
    )
    param = _typeahead()
    call = CriterionCall(
        criterion_id="c_ec",
        search_name=_SEARCH,
        text="Plasmodium genes assigned a protein kinase EC number",
        params={_PARAM: picks},
    )
    definition = WDKSearch(url_segment=_SEARCH, parameters=[param])
    refuse_a_pick_no_lookup_read(
        state, definition, call, format_param_info_typed([param])
    )
    return picks


_BROAD = "Build a comprehensive kinase strategy for Plasmodium."


def test_a_broad_request_binds_an_entry_labelled_with_the_plural() -> None:
    assert _bind(["2.7.11.-"], _BROAD, "kinase") == ["2.7.11.-"]


def test_a_broad_request_binds_an_entry_labelled_with_the_word() -> None:
    assert _bind(["2.7.1.40"], _BROAD, "kinase") == ["2.7.1.40"]


def test_a_word_that_tells_the_entries_apart_still_refuses_one_without_it() -> None:
    with pytest.raises(ModelRetry) as refused:
        _bind(["2.7.11.13"], "MAP kinase genes in Plasmodium", "MAP kinase")

    assert "['2.7.11.13'] ('2.7.11.13 (Protein kinase C.)')" in refused.value.message
