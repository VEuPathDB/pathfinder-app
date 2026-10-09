"""The GO pick of every scripted build carries the concept the request names,
so the label guard on a typeahead pick accepts it on every site."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter
from pydantic_ai import ModelRetry
from veupathdb.wdk import WDKParameter, WDKSearch
from veupathdb_mcp.catalog import PhrasingMatch, VocabLookup, format_param_info_typed

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.specs import CriterionSpec
from pathfinder.ai.models.mock.strategy_specs import (
    GO_CONCEPT,
    GO_TERM,
    combined_spec,
    go_spec,
)
from pathfinder.ai.tools.standalone._frame_lookups import refuse_a_pick_no_lookup_read
from pathfinder.ai.tools.standalone._frame_proposals import CriterionCall
from pathfinder.ai.tools.standalone._qualifier_words import proposal_values

_PARAM = "go_typeahead"
_GO_LABELS = [
    ("GO:0003735", "structural constituent of ribosome"),
    ("GO:0004672", "protein kinase activity"),
    ("GO:0016301", "kinase activity"),
    ("GO:0008233", "peptidase activity"),
    ("GO:0009986", "cell surface"),
    ("GO:0009405", "obsolete pathogenesis"),
    ("GO:0006979", "response to oxidative stress"),
    ("GO:0005618", "cell wall"),
    ("GO:0006508", "proteolysis"),
    ("GO:0006914", "autophagy"),
    ("GO:0006955", "immune response"),
    ("GO:0005840", "ribosome"),
    ("GO:0003677", "DNA binding"),
    ("GO:0005524", "ATP binding"),
]
_SITES = (
    "plasmodb",
    "toxodb",
    "cryptodb",
    "giardiadb",
    "amoebadb",
    "microsporidiadb",
    "piroplasmadb",
    "tritrypdb",
    "trichdb",
    "fungidb",
    "vectorbase",
    "hostdb",
    "veupathdb",
)


def _typeahead() -> WDKParameter:
    return TypeAdapter(WDKParameter).validate_python(
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
            "vocabulary": [
                [value, f"{value} : {label} : 4", None] for value, label in _GO_LABELS
            ],
        }
    )


def _go_criteria(values: SiteValues) -> list[CriterionSpec]:
    return [
        crit
        for build in (go_spec, combined_spec)
        for crit in build(values).criteria
        if crit.search_name == GO_TERM
    ]


def _refusals(values: SiteValues, request: str) -> list[str]:
    param = _typeahead()
    refused: list[str] = []
    for crit in _go_criteria(values):
        picks = proposal_values(crit.values[_PARAM])
        state = AgentToolState(request_messages=[request])
        state.record_lookup(
            GO_TERM,
            _PARAM,
            VocabLookup(
                terms=picks,
                matches=[
                    PhrasingMatch(
                        term=pick, phrasing=pick, reach="every_word", values=[pick]
                    )
                    for pick in picks
                ],
            ),
        )
        call = CriterionCall(
            criterion_id=crit.criterion_id,
            search_name=GO_TERM,
            text=crit.text,
            params={_PARAM: picks},
        )
        try:
            refuse_a_pick_no_lookup_read(
                state,
                WDKSearch(url_segment=GO_TERM, parameters=[param]),
                call,
                format_param_info_typed([param]),
            )
        except ModelRetry as refusal:
            refused.append(refusal.message)
    return refused


@pytest.mark.parametrize("site_id", _SITES)
def test_the_go_pick_passes_the_label_guard(site_id: str) -> None:
    values = SiteValues.for_site(site_id)
    request = f"Find {values.organism} genes annotated with {GO_CONCEPT}."

    assert _refusals(values, request) == []


@pytest.mark.parametrize("site_id", _SITES)
def test_a_request_for_another_concept_refuses_the_pick(site_id: str) -> None:
    values = SiteValues.for_site(site_id)
    request = f"Find {values.organism} genes annotated with kinase activity."

    refused = _refusals(values, request)

    assert len(refused) == len(_go_criteria(values)) == 2
    assert all("shares no uncommon word" in message for message in refused)


@pytest.mark.parametrize("site_id", _SITES)
def test_the_go_pick_is_read_under_its_parent(site_id: str) -> None:
    for crit in _go_criteria(SiteValues.for_site(site_id)):
        assert crit.values["go_term_slim"] == "No"
        assert crit.values["go_term_evidence"] == ["Curated", "Computed"]
