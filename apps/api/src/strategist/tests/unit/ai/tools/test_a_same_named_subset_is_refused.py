from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import (
    MultiPickValue,
    SinglePickValue,
    StringValue,
    VocabOption,
    read_options,
)

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone._frame_lookups import pick_problems
from strategist.ai.tools.standalone._frame_proposals import CriterionCall
from strategist.platform.refusals import refuse_problems
from strategist.tests._support.param_infos import sheet_of
from strategist.tests._support.recorded_searches import suite_search

_E1 = json.loads(
    (
        Path(__file__).resolve().parents[3]
        / "fixtures"
        / "turns"
        / "e1_serine_threonine_kinase_lookup.json"
    ).read_text()
)
_INTERPRO = "GenesByInterproDomain"
_DOMAINS = _E1["parameter"]
_MESSAGE = (
    "In Pf3D7, find genes with a serine/threonine protein kinase InterPro domain."
)
_TEXT = "Genes in Plasmodium falciparum 3D7 with a serine/threonine protein kinase InterPro domain"


def _state(message: str) -> AgentToolState:
    options = [VocabOption.model_validate(v) for v in _E1["allowedValues"]]
    read = read_options(options, _E1["query"], request_terms=[])
    assert read.lookup is not None
    state = AgentToolState()
    state.request_messages = [message]
    state.record_lookup(_INTERPRO, _DOMAINS, read.lookup, options)
    return state


def _bind(state: AgentToolState, picks: list[str]) -> None:
    call = CriterionCall(
        criterion_id="c_serine_threonine_protein_kinase_interpro",
        search_name=_INTERPRO,
        text=_TEXT,
        params={},
    ).with_values(
        {
            "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"]),
            "domain_database": SinglePickValue(value="INTERPRO"),
            _DOMAINS: MultiPickValue(values=picks),
            "domain_accession": StringValue(value="N/A"),
        }
    )
    definition = suite_search("search_genes_by_interpro_domain")
    infos = sheet_of(definition.parameters or [])
    refuse_problems(pick_problems(state, definition, call, infos))


def test_one_of_two_same_named_entries_is_refused() -> None:
    with pytest.raises(ModelRetry) as refused:
        _bind(_state(_MESSAGE), ["IPR050205"])

    assert (
        "IPR050205 and IPR050236 share the name 'SERINE/THREONINE-PROTEIN KINASE'. "
        "Bind both, or ask which one on the card."
    ) in refused.value.message


def test_both_same_named_entries_bind() -> None:
    state = _state(_MESSAGE)

    _bind(state, ["IPR050205", "IPR050236"])

    assert state.looked_up[(_INTERPRO, _DOMAINS)].same_named == {
        "SERINE/THREONINE-PROTEIN KINASE": ("IPR050205", "IPR050236")
    }


def test_an_entry_the_request_names_by_accession_binds() -> None:
    state = _state(f"{_MESSAGE} Use IPR050205.")

    _bind(state, ["IPR050205"])

    assert state.request_messages == [f"{_MESSAGE} Use IPR050205."]
