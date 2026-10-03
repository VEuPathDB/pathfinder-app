"""A new pick on a typeahead multi-pick parameter binds only an entry a lookup
of that parameter matched this pass, unless the request writes the entry out or
the criterion already holds it."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import MultiPickValue
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState, LookupRecord
from pathfinder.ai.tools.standalone._frame_lookups import refuse_a_pick_no_lookup_read
from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall
from pathfinder.domain.strategy.operational_spec import BoundValue, Criterion
from pathfinder.tests._support.recorded_searches import suite_search

_INTERPRO = "GenesByInterproDomain"
_DOMAINS = "domain_typeahead"
_TEXT = "Aedes aegypti LVP_AGWG odorant-binding protein genes"
_MESSAGE = "Aedes aegypti LVP_AGWG odorant-binding protein genes on chromosome 3."
# The OBP families a lookup of "odorant binding", "OBP" and "PBP/GOBP" matched.
_MATCHED = LookupRecord(matched={"PF01395": "odorant binding", "PF22651": "PBP/GOBP"})


def _call(picks: list[str]) -> CriterionCall:
    return CriterionCall(
        criterion_id="c_obp",
        search_name=_INTERPRO,
        text=_TEXT,
        params={
            "organism": ["Aedes aegypti LVP_AGWG"],
            "domain_database": "Pfam",
            _DOMAINS: picks,
            "domain_accession": "N/A",
        },
    )


def _state(message: str = _MESSAGE) -> AgentToolState:
    state = AgentToolState()
    state.request_messages = [message]
    return state


def _refuse(state: AgentToolState, picks: list[str]) -> None:
    definition = suite_search("search_genes_by_interpro_domain")
    infos = format_param_info_typed(definition.parameters or [])
    refuse_a_pick_no_lookup_read(state, definition, _call(picks), infos)


def test_a_pick_no_lookup_read_is_refused() -> None:
    with pytest.raises(ModelRetry) as refused:
        _refuse(_state(), ["PF03392"])

    assert (
        f"Read the options for {_TEXT!r} first, then bind the entries a phrase matched"
    ) in refused.value.message
    assert (
        f"get_parameter_options(search_name='{_INTERPRO}', parameter_id='{_DOMAINS}'"
    ) in refused.value.message


def test_a_pick_a_lookup_matched_binds() -> None:
    """The organism is a tree multi-pick, so it needs no lookup of its own."""
    state = _state()
    state.looked_up[(_INTERPRO, _DOMAINS)] = _MATCHED

    _refuse(state, ["PF01395"])

    assert state.looked_up == {(_INTERPRO, _DOMAINS): _MATCHED}


def test_a_pick_the_lookup_did_not_match_is_refused_with_its_matches() -> None:
    """The CSP family is on the name-ranked list, and no OBP phrasing matched it."""
    state = _state()
    state.looked_up[(_INTERPRO, _DOMAINS)] = _MATCHED

    with pytest.raises(ModelRetry) as refused:
        _refuse(state, ["PF01395", "PF03392"])

    assert refused.value.message.startswith(
        f"{_DOMAINS} (Specific Domain(s)) on {_INTERPRO} holds ['PF03392'], which "
        f"no lookup of it matched. Bind only entries a lookup of {_TEXT!r} "
        "returned (2: PF01395, PF22651)"
    )


def test_a_lookup_of_another_parameter_does_not_count() -> None:
    state = _state()
    state.looked_up[("GenesByLocation", "chromosomeOptional")] = LookupRecord(
        matched={"3": "chromosome 3"}
    )

    with pytest.raises(ModelRetry):
        _refuse(state, ["PF03392"])


def test_an_entry_the_request_writes_out_binds() -> None:
    state = _state("Aedes aegypti LVP_AGWG genes with PF01395 on chromosome 3.")

    _refuse(state, ["PF01395"])

    assert state.looked_up == {}


def test_a_pick_the_criterion_already_holds_binds() -> None:
    state = _state()
    state.operational_spec_draft.criteria.append(
        Criterion(
            id="c_obp",
            text=_TEXT,
            search_name=_INTERPRO,
            resolved_params={
                _DOMAINS: BoundValue(
                    value=MultiPickValue(values=["PF01395"]), source="chosen"
                )
            },
        )
    )

    _refuse(state, ["PF01395"])

    assert [c.id for c in state.operational_spec_draft.criteria] == ["c_obp"]
