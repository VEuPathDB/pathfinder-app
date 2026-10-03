"""A bound value is built once, from the published parameter sheet: its display
name, its label, whether it is a placeholder, whether it is the published
initial value and whether the site shows its parameter."""

from __future__ import annotations

from veupathdb.domain.parameters import (
    MultiPickValue,
    NumberValue,
    StringValue,
)
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
)
from pathfinder.domain.strategy.value_binding import bind_values, read_again
from pathfinder.services.strategies.parameter_rules import text_query
from pathfinder.tests._support.recorded_searches import client_search, suite_search

# plasmodb GenesByText as WDK publishes it: text_expression starts at "*reductase".
_TEXT = format_param_info_typed(
    list(suite_search("search_genes_by_text").parameters or [])
)
_LOCATION = format_param_info_typed(
    list(client_search("search_genes_by_location").parameters or [])
)
# plasmodb P. vivax IDC percentile as WDK publishes it: channel is hidden with
# two entries. GenesByOrthologPattern: profile_pattern is hidden with none.
_PERCENTILE = format_param_info_typed(
    list(
        suite_search("search_genes_by_rnaseq_pviv_patient_idc_percentile").parameters
        or []
    )
)
_ORTHOLOGS = format_param_info_typed(
    list(suite_search("search_genes_by_ortholog_pattern").parameters or [])
)
_PHRASE = "cysteine-rich protein"


def _info(sheet: list[ParameterInfo], name: str) -> ParameterInfo:
    return next(info for info in sheet if info.name == name)


def test_a_pick_is_built_with_the_display_name_and_the_labels_of_its_sheet() -> None:
    bound = bind_values(
        {"text_fields": MultiPickValue(values=["product", "Notes"])}, "chosen", _TEXT
    )

    held = bound["text_fields"]
    assert (held.display_name, held.label, held.placeholder, held.at_default) == (
        "Fields",
        "Product description, Notes from annotators",
        False,
        False,
    )


def test_a_text_at_its_published_initial_value_is_at_default() -> None:
    bound = bind_values(
        {"text_expression": StringValue(value="*reductase")}, "default", _TEXT
    )

    assert (bound["text_expression"].at_default, bound["text_expression"].unset) == (
        True,
        True,
    )


def test_a_site_prompt_is_a_placeholder() -> None:
    bound = bind_values(
        {
            "sequenceId": StringValue(value="(Example: Pf3D7_04_v3)"),
            "chromosomeOptional": StringValue(value="Choose chromosome"),
            "start_point": NumberValue(value=1),
        },
        "default",
        _LOCATION,
    )

    assert {name: (b.placeholder, b.at_default) for name, b in bound.items()} == {
        "sequenceId": (True, True),
        "chromosomeOptional": (True, True),
        "start_point": (False, True),
    }


def test_a_multi_pick_is_at_default_whatever_spacing_the_site_writes() -> None:
    organism = _info(_LOCATION, "organismSinglePick")

    held = bind_values(
        {organism.name: MultiPickValue(values=["Plasmodium falciparum 3D7"])},
        "default",
        [organism],
    )[organism.name]

    assert (organism.default_value, held.at_default) == (
        '["Plasmodium falciparum 3D7"]',
        True,
    )


def test_a_value_the_sheet_does_not_list_carries_no_sheet_fields() -> None:
    bound = bind_values({"hidden": StringValue(value="x")}, "held", _TEXT, "why")

    assert bound == {
        "hidden": BoundValue(value=StringValue(value="x"), source="held", basis="why")
    }


def test_a_value_is_judged_against_the_published_sheet_not_a_context_read() -> None:
    """A read under the bound values answers the sent text as its initial value."""
    echoed = [
        info.model_copy(update={"default_value": _PHRASE})
        if info.name == "text_expression"
        else info
        for info in _TEXT
    ]
    value = {"text_expression": StringValue(value=_PHRASE)}

    published = bind_values(value, "stated", _TEXT)["text_expression"]
    under_context = bind_values(value, "stated", echoed)["text_expression"]
    info = _info(_TEXT, "text_expression")

    assert (
        published.at_default,
        text_query(info, published),
        under_context.at_default,
    ) == (False, True, True)


def test_a_value_read_again_keeps_who_set_it_and_why() -> None:
    held = BoundValue(
        value=StringValue(value="*reductase"),
        source="chosen",
        basis="the model's reason",
        carried_from="c_option",
        stated_as="thioredoxin reductase",
    )

    read = read_again({"text_expression": held}, _TEXT)["text_expression"]

    assert read == held.model_copy(
        update={
            "display_name": "Text term (use * as wildcard)",
            "at_default": True,
        }
    )


def test_a_fold_carries_a_value_from_its_option() -> None:
    held = bind_values(
        {"text_expression": StringValue(value="kinase")}, "chosen", _TEXT
    )

    carried = held["text_expression"].carried("c_option")

    assert (carried.carried_from, carried.display_name) == (
        "c_option",
        "Text term (use * as wildcard)",
    )


def test_a_hidden_parameter_without_a_choice_is_bound_not_visible() -> None:
    bound = bind_values(
        {
            "profile_pattern": StringValue(value="hsap=1T"),
            "included_species": StringValue(value="pfal"),
        },
        "default",
        _ORTHOLOGS,
    )

    assert {name: held.visible for name, held in bound.items()} == {
        "profile_pattern": False,
        "included_species": True,
    }


def test_a_hidden_parameter_with_a_choice_is_bound_visible() -> None:
    bound = bind_values(
        {"channel": StringValue(value="Channel 1")}, "default", _PERCENTILE
    )

    assert bound["channel"].visible is True


def test_a_value_read_again_keeps_the_visibility_of_its_sheet() -> None:
    held = BoundValue(value=StringValue(value="hsap=1T"), source="default")

    read = read_again({"profile_pattern": held}, _ORTHOLOGS)["profile_pattern"]

    assert (held.visible, read.visible) == (True, False)
