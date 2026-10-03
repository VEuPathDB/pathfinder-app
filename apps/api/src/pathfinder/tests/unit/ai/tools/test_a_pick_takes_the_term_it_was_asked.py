"""A typeahead pick binds the entry whose label is the looked-up term alone when
the lookup matched one, and binds no entry the site labels obsolete unless the
request says obsolete."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter
from pydantic_ai import ModelRetry
from veupathdb.wdk import WDKParameter, WDKSearch
from veupathdb_mcp.catalog import PhrasingMatch, VocabLookup, format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_lookups import refuse_a_pick_no_lookup_read
from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall

_GO = "GenesByGoTerm"
_PARAM = "go_typeahead"
_VOCABULARY = [
    ("GO:0006955", "GO:0006955 : immune response : 3"),
    ("GO:0002250", "GO:0002250 : adaptive immune response : 4"),
    ("GO:0002218", "GO:0002218 : activation of innate immune response : 4"),
    ("GO:0006486", "GO:0006486 : obsolete protein glycosylation : 0"),
    ("GO:0018279", "GO:0018279 : obsolete protein N-linked glycosylation : 0"),
    ("GO:0006487", "GO:0006487 : protein N-linked glycosylation : 7"),
    ("GO:0006493", "GO:0006493 : protein O-linked glycosylation : 7"),
    ("GO:0009100", "GO:0009100 : obsolete glycoprotein metabolic process : 0"),
]
_GO_TYPEAHEAD: WDKParameter = TypeAdapter(WDKParameter).validate_python(
    {
        "name": _PARAM,
        "displayName": "GO Term or GO ID",
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
        "vocabulary": [[value, display, None] for value, display in _VOCABULARY],
    }
)
_DEFINITION = WDKSearch(url_segment=_GO, parameters=[_GO_TYPEAHEAD])
_INFOS = format_param_info_typed([_GO_TYPEAHEAD])
_IMMUNE = ["GO:0006955", "GO:0002250", "GO:0002218"]
_GLYCOSYLATION = ["GO:0006486", "GO:0018279", "GO:0006487", "GO:0006493"]


def _state(message: str, term: str, values: list[str]) -> AgentToolState:
    state = AgentToolState()
    state.request_messages = [message]
    state.record_lookup(
        _GO,
        _PARAM,
        VocabLookup(
            terms=[term],
            matches=[
                PhrasingMatch(term=term, phrasing=term, reach="phrase", values=values)
            ],
        ),
    )
    return state


def _bind(state: AgentToolState, text: str, picks: list[str]) -> list[str]:
    """The picks the call binds; a refusal raises instead."""
    call = CriterionCall(
        criterion_id="c_go", search_name=_GO, text=text, params={_PARAM: picks}
    )
    refuse_a_pick_no_lookup_read(state, _DEFINITION, call, _INFOS)
    return picks


def _immune(picks: list[str], message: str = "Genes for immune response.") -> list[str]:
    return _bind(_state(message, "immune response", _IMMUNE), "immune response", picks)


_NARROWER_REFUSED = (
    f"{_PARAM} (GO Term or GO ID) on {_GO} holds ['GO:0002250'], which the "
    "lookup of 'immune response' matched beside GO:0006955 "
    "('GO:0006955 : immune response : 3'), the entry whose label is that term. "
    "Bind the exact entry alone; the others state a narrower or related "
    "question, unless the request names them."
)


def test_a_narrower_pick_without_the_exact_term_is_refused() -> None:
    with pytest.raises(ModelRetry) as refused:
        _immune(["GO:0002250"])

    assert refused.value.message == _NARROWER_REFUSED


def test_the_exact_term_with_a_narrower_one_is_refused() -> None:
    with pytest.raises(ModelRetry) as refused:
        _immune(["GO:0006955", "GO:0002250"])

    assert refused.value.message == _NARROWER_REFUSED


def test_the_exact_term_alone_binds() -> None:
    assert _immune(["GO:0006955"]) == ["GO:0006955"]


def test_a_narrower_pick_written_out_binds_beside_the_exact_term() -> None:
    assert _immune(
        ["GO:0006955", "GO:0002250"],
        "Genes for immune response, and for adaptive immune response.",
    ) == ["GO:0006955", "GO:0002250"]


def test_an_entry_another_term_matched_is_untouched() -> None:
    state = _state("Genes for immune response.", "immune response", ["GO:0006955"])
    state.record_lookup(
        _GO,
        _PARAM,
        VocabLookup(
            terms=["adaptive immunity"],
            matches=[
                PhrasingMatch(
                    term="adaptive immunity",
                    phrasing="adaptive immunity",
                    reach="phrase",
                    values=["GO:0002250"],
                )
            ],
        ),
    )

    assert _bind(state, "immune response", ["GO:0006955", "GO:0002250"]) == [
        "GO:0006955",
        "GO:0002250",
    ]


def test_a_narrower_pick_the_request_writes_out_binds() -> None:
    assert _immune(["GO:0002250"], "Genes for adaptive immune response.") == [
        "GO:0002250"
    ]


def test_a_pick_binds_when_no_entry_is_the_exact_term() -> None:
    state = _state(
        "Genes for innate immunity.", "innate immunity", ["GO:0002218", "GO:0002250"]
    )

    assert _bind(state, "innate immunity", ["GO:0002218"]) == ["GO:0002218"]


def _glycosylation(picks: list[str], message: str) -> list[str]:
    state = _state(message, "protein glycosylation", _GLYCOSYLATION)
    return _bind(state, "protein glycosylation", picks)


def test_an_obsolete_pick_is_refused_with_the_current_entries() -> None:
    with pytest.raises(ModelRetry) as refused:
        _glycosylation(["GO:0006486", "GO:0018279"], "Protein glycosylation genes.")

    assert refused.value.message == (
        f"{_PARAM} (GO Term or GO ID) on {_GO} holds ['GO:0006486', 'GO:0018279'], "
        "which the site labels obsolete, and no request message says obsolete. "
        "The lookup of 'protein glycosylation' matched these current entries: "
        "GO:0006487 ('GO:0006487 : protein N-linked glycosylation : 7'), "
        "GO:0006493 ('GO:0006493 : protein O-linked glycosylation : 7'). Bind "
        "current entries, or ask the researcher which one they mean."
    )


def test_an_obsolete_pick_with_no_current_match_says_so() -> None:
    state = _state("Glycoprotein genes.", "glycoprotein", ["GO:0009100"])

    with pytest.raises(ModelRetry) as refused:
        _bind(state, "glycoprotein", ["GO:0009100"])

    assert "The lookup of 'glycoprotein' matched no current entry." in (
        refused.value.message
    )


def test_an_obsolete_pick_binds_when_the_request_says_obsolete() -> None:
    assert _glycosylation(
        ["GO:0006486"], "Genes under the obsolete glycosylation terms."
    ) == ["GO:0006486"]


def test_a_current_pick_binds() -> None:
    assert _glycosylation(
        ["GO:0006487", "GO:0006493"], "Protein glycosylation genes."
    ) == ["GO:0006487", "GO:0006493"]
