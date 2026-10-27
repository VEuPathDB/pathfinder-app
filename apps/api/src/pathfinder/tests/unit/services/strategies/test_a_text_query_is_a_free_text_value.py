"""A text query is the value of a free-text parameter that states something
the site does not already send, as its sheet read it when it bound; a
placeholder, the radio-off value, the sheet default, a vocabulary term, a number
and a phyletic pattern are none."""

from __future__ import annotations

import json
from typing import Any

import pytest
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb.errors import WDKError
from veupathdb.testing.fixture_store import FIXTURE_ROOT
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.value_binding import bind_values
from pathfinder.services.strategies import search_sheets
from pathfinder.services.strategies.parameter_rules import text_query
from pathfinder.services.strategies.search_sheets import search_definitions
from pathfinder.tests._support.logs import logged_events
from pathfinder.tests._support.qa_recording import qa_recording
from pathfinder.tests._support.recorded_searches import suite_search


def _info(name: str, param_type: str = "string", **fields: object) -> ParameterInfo:
    return ParameterInfo.model_validate(
        {
            "name": name,
            "display_name": name,
            "type": param_type,
            "required": True,
            "is_visible": True,
            "help": "",
            "value_format": "",
            **fields,
        }
    )


def free_text_params(
    criterion: Criterion, infos: list[ParameterInfo]
) -> frozenset[str]:
    by_name = {info.name: info for info in infos}
    return frozenset(
        name
        for name, held in criterion.resolved_params.items()
        if name in by_name and text_query(by_name[name], held)
    )


def _criterion(
    search: str, values: dict[str, ParamValue], sheet: list[ParameterInfo]
) -> Criterion:
    return Criterion(
        id=f"c_{search}",
        text=search,
        search_name=search,
        resolved_params=bind_values(values, "stated", sheet),
    )


def test_a_placeholder_go_term_is_no_text_query() -> None:
    infos = [
        _info("go_typeahead", "multi-pick-vocabulary"),
        _info("go_term", display_name="GO Term wildcard search", default_value="N/A"),
    ]
    criterion = _criterion(
        "GenesByGoTerm",
        {
            "go_typeahead": MultiPickValue(values=["GO:0004672"]),
            "go_term": StringValue(value="N/A"),
        },
        infos,
    )

    assert free_text_params(criterion, infos) == frozenset()


def _recorded(fixture: str) -> list[ParameterInfo]:
    return format_param_info_typed(suite_search(fixture).parameters or [])


def test_the_radio_off_domain_accession_is_no_text_query() -> None:
    infos = _recorded("search_genes_by_interpro_domain")
    criterion = _criterion(
        "GenesByInterproDomain",
        {
            "domain_typeahead": MultiPickValue(values=["PF05795", "PF09687"]),
            "domain_accession": StringValue(value="N/A"),
        },
        infos,
    )
    accession = next(i for i in infos if i.name == "domain_accession")

    assert (accession.default_value, free_text_params(criterion, infos)) == (
        "",
        frozenset(),
    )


def test_a_phyletic_pattern_and_its_species_lists_are_no_text_query() -> None:
    criterion = _criterion(
        "GenesByOrthologPattern",
        {
            "profile_pattern": StringValue(value="%hsap:N%"),
            "included_species": StringValue(value="n/a"),
            "excluded_species": StringValue(value="hsap"),
        },
        _recorded("search_genes_by_ortholog_pattern"),
    )

    assert (
        free_text_params(criterion, _recorded("search_genes_by_ortholog_pattern"))
        == frozenset()
    )


def test_a_free_text_value_is_a_text_query() -> None:
    infos = [
        _info("text_expression", default_value=""),
        _info("text_search_organism", "multi-pick-vocabulary"),
    ]
    criterion = _criterion(
        "GenesByText",
        {
            "text_expression": StringValue(value="trans-sialidase"),
            "text_search_organism": MultiPickValue(
                values=["Trypanosoma cruzi Dm28c 2018"]
            ),
        },
        infos,
    )

    assert free_text_params(criterion, infos) == frozenset({"text_expression"})


def _location_search() -> WDKSearch:
    recorded = json.loads(
        qa_recording(FIXTURE_ROOT / "wdk" / "search_genes_by_location.json").read_text()
    )
    return WDKSearch.model_validate(recorded["body"]["searchData"])


def _location_sheet() -> list[ParameterInfo]:
    return format_param_info_typed(_location_search().parameters or [])


def test_a_location_step_at_its_placeholder_sequence_binds_no_text_query() -> None:
    location = _criterion(
        "GenesByLocation",
        {
            "organismSinglePick": MultiPickValue(values=["Plasmodium falciparum 3D7"]),
            "chromosomeOptional": SinglePickValue(value="Pf3D7_06_v3"),
            "sequenceId": StringValue(value="(Example: Pf3D7_04_v3)"),
            "start_point": StringValue(value="1"),
            "end_point": StringValue(value="0"),
        },
        _location_sheet(),
    )

    assert free_text_params(location, _location_sheet()) == frozenset()


def test_a_sequence_the_researcher_typed_is_a_text_query() -> None:
    location = _criterion(
        "GenesByLocation",
        {"sequenceId": StringValue(value="Pf3D7_06_v3")},
        _location_sheet(),
    )

    assert free_text_params(location, _location_sheet()) == frozenset({"sequenceId"})


async def test_a_search_the_catalog_cannot_read_has_no_sheet(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def _listed(_site: str, names: Any) -> dict[str, str]:
        return dict.fromkeys(names, "transcript")

    async def _unreadable(*_args: Any, **_kwargs: Any) -> WDKSearch:
        detail = "the sheet did not load"
        raise WDKError(detail)

    monkeypatch.setattr(search_sheets, "search_record_types", _listed)
    monkeypatch.setattr(search_sheets, "read_search_definition", _unreadable)
    typed = _criterion(
        "GenesByText", {"text_expression": StringValue(value="kinase")}, []
    )
    spec = OperationalSpec(goal="kinases", criteria=[typed])

    sheets = await search_definitions("plasmodb", spec)

    assert sheets == {}
    assert logged_events(caplog.records) == ["search sheet unreadable"]


async def test_a_sheet_is_read_under_the_record_type_that_lists_its_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A BLAST criterion of an OrthoMCL spec is read as a protein search."""
    read_under: list[str] = []

    async def _listed(_site: str, names: Any) -> dict[str, str]:
        return {name: "sequence" for name in names if name == "ByBlast"}

    async def _definition(_site: str, record_type: str, name: str) -> WDKSearch:
        read_under.append(record_type)
        return WDKSearch(url_segment=name)

    monkeypatch.setattr(search_sheets, "search_record_types", _listed)
    monkeypatch.setattr(search_sheets, "read_search_definition", _definition)
    blast = _criterion(
        "ByBlast",
        {"BlastQuerySequence": StringValue(value="MPENNEHLTF")},
        [_info("BlastQuerySequence")],
    )

    await search_definitions(
        "orthomcl", OperationalSpec(goal="BLAST a protein", criteria=[blast])
    )

    assert read_under == ["sequence"]


async def test_a_search_the_catalog_does_not_list_reads_no_sheet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read: list[tuple[str, str]] = []

    async def _listed(_site: str, _names: Any) -> dict[str, str]:
        return {}

    async def _definition(_site: str, record_type: str, name: str) -> WDKSearch:
        read.append((record_type, name))
        return WDKSearch(url_segment=name)

    monkeypatch.setattr(search_sheets, "search_record_types", _listed)
    monkeypatch.setattr(search_sheets, "read_search_definition", _definition)
    typed = _criterion(
        "GenesByText", {"text_expression": StringValue(value="kinase")}, []
    )
    spec = OperationalSpec(goal="kinases", criteria=[typed])

    assert (await search_definitions("plasmodb", spec), read) == ({}, [])
