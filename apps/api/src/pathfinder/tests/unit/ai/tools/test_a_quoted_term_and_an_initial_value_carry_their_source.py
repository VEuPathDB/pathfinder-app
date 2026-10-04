"""A text term the message writes in quotes is stated whole, a number at the
initial value the site publishes is the site's unless the message names its
parameter, and no number is cut from a requirement phrase."""

from __future__ import annotations

from veupathdb.domain.parameters import StringValue
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.tools.standalone._frame_sources import bound_values
from pathfinder.tests._support.recorded_searches import client_search, suite_search

_QUOTED = 'I meant the exact phrase "GPI anchored", in quotes'
_GPI_PHRASE = "exact quoted phrase GPI anchored"


def _text_term(text: str, message: str, requirement: str) -> tuple[str, str]:
    held = bound_values(
        {"text_expression": StringValue(value=text)},
        infos=format_param_info_typed(
            suite_search("search_genes_by_text").parameters or []
        ),
        site_supplied=set(),
        request_texts=[message],
        reason="the model's reason",
        requirement_phrases=[requirement],
    )["text_expression"]
    return held.source, held.basis


def _location(
    values: dict[str, str], message: str, requirements: list[str]
) -> dict[str, tuple[str, bool]]:
    """The plasmodb GenesByLocation sheet publishes start 1 and end 0."""
    bound = bound_values(
        {name: StringValue(value=value) for name, value in values.items()},
        infos=format_param_info_typed(
            client_search("search_genes_by_location").parameters or []
        ),
        site_supplied=set(),
        request_texts=[message],
        reason="the model's reason",
        requirement_phrases=requirements,
    )
    return {name: (held.source, held.at_default) for name, held in bound.items()}


def test_a_term_the_message_quotes_is_stated_whatever_the_requirement_writes() -> None:
    assert _text_term('"GPI anchored"', _QUOTED, _GPI_PHRASE) == (
        "stated",
        "GPI anchored",
    )


def test_the_quoted_term_is_matched_with_its_case_folded() -> None:
    assert _text_term(
        '"GPI anchored"', 'the exact phrase "gpi Anchored" please', _GPI_PHRASE
    ) == ("stated", "gpi Anchored")


def test_a_term_between_curly_quotes_is_quoted_too() -> None:
    curly = f"the exact phrase {chr(0x201C)}GPI anchored{chr(0x201D)}"

    assert _text_term('"GPI anchored"', curly, _GPI_PHRASE) == (
        "stated",
        "GPI anchored",
    )


def test_a_term_cut_from_a_longer_quoted_phrase_is_still_chosen() -> None:
    assert _text_term(
        "erythrocyte surface antigen",
        'genes with a "variant erythrocyte surface antigen" annotation',
        "variant erythrocyte surface antigen annotation",
    ) == ("chosen", "the model's reason")


def test_the_start_at_its_published_initial_value_is_the_sites() -> None:
    assert _location(
        {"start_point": "1", "end_point": "0"},
        "Genes on chromosome 1 of Plasmodium falciparum 3D7",
        ["chromosome 1", "Plasmodium falciparum 3D7"],
    ) == {"start_point": ("default", True), "end_point": ("default", True)}


def test_an_initial_value_the_message_writes_beside_its_name_is_stated() -> None:
    assert _location(
        {"start_point": "1"}, "Genes on chromosome 1 that start at 1", []
    ) == {"start_point": ("stated", True)}


def test_a_number_the_message_states_is_never_cut_from_a_phrase() -> None:
    assert _location(
        {"start_point": "1000", "end_point": "5000"},
        "Genes on chromosome 1 from 1000 to 5000",
        ["chromosome 1 positions 1000 to 5000"],
    ) == {"start_point": ("stated", False), "end_point": ("stated", False)}
