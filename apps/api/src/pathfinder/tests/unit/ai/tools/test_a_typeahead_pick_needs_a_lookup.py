"""A new pick on a typeahead multi-pick parameter binds only after a lookup
of that parameter this pass, unless the request writes the entry out or the
criterion already holds it."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import MultiPickValue

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_lookups import refuse_a_pick_no_lookup_read
from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall
from pathfinder.domain.strategy.operational_spec import BoundValue, Criterion
from pathfinder.tests._support.recorded_searches import suite_search

_INTERPRO = "GenesByInterproDomain"
_DOMAINS = "domain_typeahead"
_TEXT = "Aedes aegypti LVP_AGWG odorant-binding protein genes"
_MESSAGE = "Aedes aegypti LVP_AGWG odorant-binding protein genes on chromosome 3."


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
    refuse_a_pick_no_lookup_read(
        state, suite_search("search_genes_by_interpro_domain"), _call(picks)
    )


def test_a_pick_no_lookup_read_is_refused() -> None:
    with pytest.raises(ModelRetry) as refused:
        _refuse(_state(), ["PF03392"])

    assert (
        f"Read the options for {_TEXT!r} first, then bind the entries a phrase matched"
    ) in refused.value.message
    assert (
        f"get_parameter_options(search_name='{_INTERPRO}', parameter_id='{_DOMAINS}'"
    ) in refused.value.message


def test_a_pick_after_a_lookup_of_the_parameter_binds() -> None:
    """The organism is a tree multi-pick, so it needs no lookup of its own."""
    state = _state()
    state.looked_up.add((_INTERPRO, _DOMAINS))

    _refuse(state, ["PF01395"])


def test_a_lookup_of_another_parameter_does_not_count() -> None:
    state = _state()
    state.looked_up.add(("GenesByLocation", "chromosomeOptional"))

    with pytest.raises(ModelRetry):
        _refuse(state, ["PF03392"])


def test_an_entry_the_request_writes_out_binds() -> None:
    _refuse(
        _state("Aedes aegypti LVP_AGWG genes with PF01395 on chromosome 3."),
        ["PF01395"],
    )


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
