from __future__ import annotations

import json
from pathlib import Path

import pytest
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    VocabOption,
)
from veupathdb_mcp.catalog import ParameterInfo

from strategist.ai.lead.parameter_facts import step_parameters
from strategist.ai.tools.standalone._frame_datasets import with_typed_ids
from strategist.ai.tools.standalone._frame_sources import (
    bound_values,
    stated_by_their_labels,
    stated_by_their_taxa,
)
from strategist.domain.strategy.named_taxa import organism_trees
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
)
from strategist.domain.strategy.value_source import ParamSheet, value_source
from strategist.services.strategies.pick_readings import options_not_taken
from strategist.tests._support.param_infos import sheet_of
from strategist.tests._support.recorded_searches import client_search, suite_search

_E10 = json.loads(
    (
        Path(__file__).resolve().parents[3]
        / "fixtures"
        / "turns"
        / "e10_domain_database.json"
    ).read_text()
)
_MESSAGE: str = _E10["message"]
_DATABASE = "domain_database"


def _interpro_sheet() -> list[ParameterInfo]:
    return sheet_of(suite_search("search_genes_by_interpro_domain").parameters or [])


def _database(value: ParamValue, message: str) -> BoundValue:
    return bound_values(
        {_DATABASE: value},
        infos=_interpro_sheet(),
        site_supplied=set(),
        request_texts=[message],
        reason="The model picked it.",
    )[_DATABASE]


def test_the_e10_request_names_interpro_beside_the_bound_pfam() -> None:
    assert _database(SinglePickValue(value="Pfam"), _MESSAGE).source == "chosen"


def test_a_request_that_names_interpro_alone_states_it() -> None:
    bound = _database(SinglePickValue(value="INTERPRO"), "An InterPro search in H348.")

    assert (bound.source, bound.basis) == ("stated", "InterPro")


def test_interpro_bound_where_the_request_also_names_pfam_is_chosen() -> None:
    assert _database(SinglePickValue(value="INTERPRO"), _MESSAGE).source == "chosen"


def test_both_named_entries_bound_are_stated() -> None:
    vocabulary = [
        VocabOption.model_validate(v) for v in _E10["domainDatabase"]["vocabulary"]
    ]

    found = value_source(
        MultiPickValue(values=["Pfam", "INTERPRO"]),
        placeholder=False,
        unset=False,
        request_texts=[_MESSAGE],
        sheet=ParamSheet(display_name="Domain Database", vocabulary=tuple(vocabulary)),
    )

    assert found != "chosen"
    assert found not in ("default", "card")


def test_a_label_restatement_takes_the_named_alternative_into_account() -> None:
    held = BoundValue(value=SinglePickValue(value="Pfam"), source="chosen")
    labels = [Measurement(kind="vocabulary_label", param=_DATABASE, label="Pfam")]

    restated = stated_by_their_labels(
        {_DATABASE: held}, labels, _interpro_sheet(), [_MESSAGE]
    )

    assert restated[_DATABASE].source == "chosen"


def test_a_dataset_restatement_reads_the_parameters_vocabulary() -> None:
    held = BoundValue(value=SinglePickValue(value="ds_1"), source="chosen")

    restated = with_typed_ids(
        {"ds_param": held}, {"ds_param": ["PF3D7_0100100"]}, ["Use PF3D7_0100100."]
    )

    assert (restated["ds_param"].source, restated["ds_param"].basis) == (
        "stated",
        "PF3D7_0100100",
    )


@pytest.mark.parametrize(
    ("message", "source"),
    [
        ("Genes of Plasmodium falciparum 3D7.", "stated"),
        (
            "Genes of Plasmodium falciparum 3D7 or Plasmodium vivax P01.",
            "chosen",
        ),
    ],
)
def test_an_organism_named_beside_another_is_a_choice(
    message: str, source: str
) -> None:
    taxon_search = client_search("search_genes_by_taxon")
    trees = organism_trees(taxon_search)
    [organism] = list(trees)
    held = BoundValue(
        value=MultiPickValue(values=["Plasmodium falciparum 3D7"]), source="chosen"
    )
    labels = [
        Measurement(
            kind="vocabulary_label",
            param=organism,
            label="Plasmodium falciparum 3D7",
        )
    ]

    restated = stated_by_their_labels(
        {organism: held}, labels, sheet_of(taxon_search.parameters or []), [message]
    )

    assert restated[organism].source == source
    assert (
        stated_by_their_taxa(
            restated, trees, [message], sheet_of(taxon_search.parameters or [])
        )[organism].source
        == source
    )


def test_the_facts_show_the_e10_database_as_chosen_with_interpro_untaken() -> None:
    sheet = {info.name: info for info in _interpro_sheet()}
    bound = _database(SinglePickValue(value="Pfam"), _MESSAGE)
    criterion = Criterion(
        id="c_domain_family",
        text="InterPro/Pfam polar tube protein family search",
        search_name="GenesByInterproDomain",
        resolved_params={_DATABASE: bound},
        param_display_names={_DATABASE: "Domain Database"},
        measurements=options_not_taken(_DATABASE, bound.value, sheet[_DATABASE]),
    )

    [fact] = [
        f
        for f in step_parameters(criterion, "genes", [_MESSAGE], [])
        if f.name == _DATABASE
    ]

    assert fact.source == "chosen"
    assert any("did not take" in note and "INTERPRO" in note for note in fact.notes)
