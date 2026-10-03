"""A new typeahead pick shares an uncommon content word with the request, or the
request writes the picked label out."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter
from pydantic_ai import ModelRetry
from veupathdb.wdk import WDKParameter, WDKSearch
from veupathdb_mcp.catalog import PhrasingMatch, VocabLookup, format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_lookups import refuse_a_pick_no_lookup_read
from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall

_SEARCH = "GenesByInterproDomain"
_PARAM = "domain_typeahead"
_REQUEST = "Aedes aegypti LVP_AGWG odorant-binding protein genes on chromosome 3"
_CONCEPT = "odorant-binding protein"
_PFAM = [
    ("PF03392", "Insect pheromone-binding family, A10/OS-D"),
    ("PF01395", "PBP/GOBP family"),
    ("IPR006170", "Pheromone/general odorant binding protein domain"),
    ("PF00036", "EF-hand calcium binding protein"),
    ("PF00071", "Ras GTP binding protein"),
    ("PF00076", "RNA recognition motif binding protein"),
    ("PF00169", "Pleckstrin homology binding domain"),
    ("PF00400", "WD40 repeat binding protein"),
    ("PF00010", "Helix-loop-helix DNA-binding protein"),
    ("PF00046", "Homeodomain DNA-binding protein"),
    ("PF00096", "Zinc finger C2H2 binding protein"),
    ("PF00134", "Cyclin N-terminal binding domain"),
    ("PF00017", "SH2 phosphotyrosine binding domain"),
]


def _typeahead(vocabulary: list[tuple[str, str]]) -> WDKParameter:
    return TypeAdapter(WDKParameter).validate_python(
        {
            "name": _PARAM,
            "displayName": "InterPro domain",
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
            "vocabulary": [[value, display, None] for value, display in vocabulary],
        }
    )


def _bind(
    picks: list[str],
    message: str = _REQUEST,
    vocabulary: list[tuple[str, str]] = _PFAM,
) -> list[str]:
    """The picks the call binds; a refusal raises instead."""
    state = AgentToolState()
    state.request_messages = [message]
    state.record_lookup(
        _SEARCH,
        _PARAM,
        VocabLookup(
            terms=[_CONCEPT],
            matches=[
                PhrasingMatch(
                    term=_CONCEPT,
                    phrasing="odorant binding protein",
                    reach="every_word",
                    values=[value for value, _ in vocabulary],
                )
            ],
        ),
    )
    param = _typeahead(vocabulary)
    call = CriterionCall(
        criterion_id="c_obp",
        search_name=_SEARCH,
        text=_CONCEPT,
        params={_PARAM: picks},
    )
    definition = WDKSearch(url_segment=_SEARCH, parameters=[param])
    refuse_a_pick_no_lookup_read(
        state, definition, call, format_param_info_typed([param])
    )
    return picks


def test_a_pick_that_shares_only_a_common_word_is_refused() -> None:
    with pytest.raises(ModelRetry) as refused:
        _bind(["PF03392"])

    assert refused.value.message == (
        f"{_PARAM} (InterPro domain) on {_SEARCH} holds ['PF03392'] ('Insect "
        "pheromone-binding family, A10/OS-D'), whose label shares no uncommon "
        "word with the request's 'odorant-binding protein'. The lookup matched "
        "entries whose labels carry the request's words: IPR006170 "
        "('Pheromone/general odorant binding protein domain'). Bind an entry "
        "whose label carries the concept's words, or ask the researcher which "
        "family they mean."
    )


def test_a_lookup_that_matched_no_fitting_entry_says_so() -> None:
    without_obp = [entry for entry in _PFAM if entry[0] != "IPR006170"]

    with pytest.raises(ModelRetry) as refused:
        _bind(["PF03392"], vocabulary=without_obp)

    assert (
        "No entry this lookup matched carries the request's words; read the "
        "options. Bind an entry"
    ) in refused.value.message


def test_a_pick_that_shares_no_word_is_refused() -> None:
    with pytest.raises(ModelRetry) as refused:
        _bind(["PF01395"])

    assert "['PF01395'] ('PBP/GOBP family')" in refused.value.message


def test_a_pick_that_shares_an_uncommon_word_binds() -> None:
    assert _bind(["IPR006170"]) == ["IPR006170"]


def test_a_pick_the_request_writes_out_binds() -> None:
    message = "Genes of the Insect pheromone-binding family, A10/OS-D on chromosome 3"

    assert _bind(["PF03392"], message) == ["PF03392"]


def test_a_small_vocabulary_binds_on_any_shared_word() -> None:
    small = _PFAM[:5]

    assert _bind(["PF03392"], vocabulary=small) == ["PF03392"]
