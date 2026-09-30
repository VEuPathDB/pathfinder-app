"""A text query is the value of a free-text parameter that is not unset; a
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

from pathfinder.domain.evidence import (
    RequirementCheck,
    SampledGene,
    VerificationReview,
)
from pathfinder.domain.shown_requirements import TextQuery, held_to_the_records
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.services.strategies import text_queries
from pathfinder.services.strategies.text_queries import (
    free_text_params,
    search_definitions,
    text_query_criteria,
)
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests._support.logs import logged_events
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


def _criterion(
    search: str, values: dict[str, ParamValue], defaulted: tuple[str, ...] = ()
) -> Criterion:
    return Criterion(
        id=f"c_{search}",
        text=search,
        search_name=search,
        resolved_params=bound(values, defaulted=defaulted),
    )


def test_a_placeholder_go_term_is_no_text_query() -> None:
    criterion = _criterion(
        "GenesByGoTerm",
        {
            "go_typeahead": MultiPickValue(values=["GO:0004672"]),
            "go_term": StringValue(value="N/A"),
        },
        defaulted=("go_term",),
    )
    infos = [
        _info("go_typeahead", "multi-pick-vocabulary"),
        _info("go_term", display_name="GO Term wildcard search", default_value="N/A"),
    ]

    assert free_text_params(criterion, infos) == frozenset()


def _recorded(fixture: str) -> list[ParameterInfo]:
    return format_param_info_typed(suite_search(fixture).parameters or [])


def test_the_radio_off_domain_accession_is_no_text_query() -> None:
    criterion = _criterion(
        "GenesByInterproDomain",
        {
            "domain_typeahead": MultiPickValue(values=["PF05795", "PF09687"]),
            "domain_accession": StringValue(value="N/A"),
        },
        defaulted=("domain_accession",),
    )
    infos = _recorded("search_genes_by_interpro_domain")
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
    )

    assert (
        free_text_params(criterion, _recorded("search_genes_by_ortholog_pattern"))
        == frozenset()
    )


def test_a_free_text_value_is_a_text_query() -> None:
    criterion = _criterion(
        "GenesByText",
        {
            "text_expression": StringValue(value="trans-sialidase"),
            "text_search_organism": MultiPickValue(
                values=["Trypanosoma cruzi Dm28c 2018"]
            ),
        },
    )
    infos = [
        _info("text_expression", default_value=""),
        _info("text_search_organism", "multi-pick-vocabulary"),
    ]

    assert free_text_params(criterion, infos) == frozenset({"text_expression"})


def _location_search() -> WDKSearch:
    recorded = json.loads(
        (FIXTURE_ROOT / "wdk" / "search_genes_by_location.json").read_text()
    )
    return WDKSearch.model_validate(recorded["body"]["searchData"])


@pytest.fixture
def location_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _record_type(*_args: Any, **_kwargs: Any) -> str:
        return "transcript"

    async def _definition(*_args: Any, **_kwargs: Any) -> WDKSearch:
        return _location_search()

    monkeypatch.setattr(text_queries, "resolve_search_record_type", _record_type)
    monkeypatch.setattr(text_queries, "read_search_definition", _definition)


@pytest.mark.usefixtures("location_catalog")
async def test_a_location_step_at_its_placeholder_sequence_binds_no_text_query() -> (
    None
):
    location = _criterion(
        "GenesByLocation",
        {
            "organismSinglePick": MultiPickValue(values=["Plasmodium falciparum 3D7"]),
            "chromosomeOptional": SinglePickValue(value="Pf3D7_06_v3"),
            "sequenceId": StringValue(value="(Example: Pf3D7_04_v3)"),
            "start_point": StringValue(value="1"),
            "end_point": StringValue(value="0"),
        },
        defaulted=("sequenceId", "start_point", "end_point"),
    )
    spec = OperationalSpec(goal="chromosome 6 genes", criteria=[location])

    assert text_query_criteria(spec, await search_definitions("plasmodb", spec)) == []


@pytest.mark.usefixtures("location_catalog")
async def test_a_sequence_the_researcher_typed_is_a_text_query() -> None:
    location = _criterion(
        "GenesByLocation",
        {"sequenceId": StringValue(value="Pf3D7_06_v3")},
    )
    spec = OperationalSpec(goal="genes on one contig", criteria=[location])

    assert text_query_criteria(spec, await search_definitions("plasmodb", spec)) == [
        TextQuery(
            criterion_id="c_GenesByLocation",
            param="sequenceId",
            value="Pf3D7_06_v3",
        )
    ]


async def test_a_search_the_catalog_cannot_read_binds_no_text_query(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def _record_type(*_args: Any, **_kwargs: Any) -> str:
        return "transcript"

    async def _unreadable(*_args: Any, **_kwargs: Any) -> WDKSearch:
        detail = "the sheet did not load"
        raise WDKError(detail)

    monkeypatch.setattr(text_queries, "resolve_search_record_type", _record_type)
    monkeypatch.setattr(text_queries, "read_search_definition", _unreadable)
    typed = _criterion("GenesByText", {"text_expression": StringValue(value="kinase")})
    spec = OperationalSpec(goal="kinases", criteria=[typed])

    sheets = await search_definitions("plasmodb", spec)

    assert (sheets, text_query_criteria(spec, sheets)) == ({}, [])
    assert logged_events(caplog.records) == ["search sheet unreadable"]


def _recorded_sheets() -> dict[str, WDKSearch]:
    return {
        "GenesByInterproDomain": suite_search("search_genes_by_interpro_domain"),
        "GenesByOrthologPattern": suite_search("search_genes_by_ortholog_pattern"),
    }


def test_the_knowlesi_organism_and_domain_rows_stand_met_on_unclear_records() -> None:
    domain = Criterion(
        id="step_a6bb905a",
        text="with a Plasmodium-specific domain",
        search_name="GenesByInterproDomain",
        resolved_params=bound(
            {
                "organism": MultiPickValue(values=["Plasmodium knowlesi strain H"]),
                "domain_database": SinglePickValue(value="Pfam"),
                "domain_typeahead": MultiPickValue(
                    values=[
                        "PF05795",
                        "PF09687",
                        "PF09717",
                        "PF12319",
                        "PF18680",
                        "PF11567",
                    ]
                ),
                "domain_accession": StringValue(value="N/A"),
            },
            defaulted=("domain_database", "domain_accession"),
        ),
    )
    ortholog = Criterion(
        id="step_bd8bb1e3",
        text="that have no ortholog in Homo sapiens",
        search_name="GenesByOrthologPattern",
        resolved_params=bound(
            {
                "organism": MultiPickValue(values=["Plasmodium knowlesi strain H"]),
                "profile_pattern": StringValue(value="%hsap:N%"),
                "excluded_species": StringValue(value="hsap"),
                "included_species": StringValue(value="n/a"),
            }
        ),
    )
    spec = OperationalSpec(
        goal="P. knowlesi strain H genes with a Plasmodium-specific domain",
        criteria=[domain, ortholog],
    )
    rows = [
        RequirementCheck(
            text=text,
            turn=1,
            answered_by=answered_by,
            how="parameter",
            status="met",
            note="the step binds it",
        )
        for text, answered_by in (
            ("Plasmodium knowlesi strain H genes", ["step_a6bb905a", "step_bd8bb1e3"]),
            ("with a Plasmodium-specific domain", ["step_a6bb905a"]),
        )
    ]
    review = VerificationReview(
        requirements=rows,
        sampled_genes=[
            SampledGene(
                gene_id=gene_id,
                product=product,
                organism="P. knowlesi strain H",
                fits="unclear",
                why="the record does not show the bound Pfam annotation",
            )
            for gene_id, product in (
                ("PKNH_0202800", "PIR protein"),
                (
                    "PKNH_0508100",
                    "Plasmodium exported protein (PHIST), unknown function",
                ),
            )
        ],
    )

    queries = text_query_criteria(spec, _recorded_sheets())

    assert (queries, held_to_the_records(review, queries)) == ([], review)
