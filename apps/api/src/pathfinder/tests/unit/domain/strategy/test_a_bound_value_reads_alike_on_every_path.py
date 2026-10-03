"""A value bound on one published sheet holds the same label, display name,
placeholder and default marks whether the bind, the hydration, a replay or a
fold built it; only who set it differs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from hypothesis import given, settings
from hypothesis import strategies as st
from veupathdb.domain.parameters import (
    MultiPickValue,
    NumberValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb.wdk import WDKParameter, WDKSearch
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.ai.tools.standalone._frame_sources import bound_values
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
)
from pathfinder.domain.strategy.spec_hydration import sheet_marked
from pathfinder.domain.strategy.spec_replay import criterion_restated
from pathfinder.domain.strategy.value_binding import bind_values
from pathfinder.tests._support.recorded_searches import client_search, suite_search

_TEXT_SEARCH = suite_search("search_genes_by_text")
_LOCATION_SEARCH = client_search("search_genes_by_location")
_INTERPRO_SEARCH = suite_search("search_genes_by_interpro_domain")
# Two fungidb GO terms a lookup of "lipase" returned: one label holds the word.
_GO_TERMS = [
    ["GO:0016298", "lipase activity", None],
    [
        "GO:0007200",
        "phospholipase C-activating G protein-coupled receptor signaling pathway",
        None,
    ],
]
_MESSAGE = "Aspergillus nidulans genes annotated with lipase activity."


def _sheet(search: WDKSearch) -> list[ParameterInfo]:
    return format_param_info_typed(list(search.parameters or []))


def _go_sheet() -> list[ParameterInfo]:
    """A GO typeahead entry, shaped as WDK publishes a typeahead multi-pick."""
    typeahead = next(
        p for p in _INTERPRO_SEARCH.parameters or [] if p.name == "domain_typeahead"
    )
    body = typeahead.model_dump(by_alias=True, mode="json") | {
        "name": "go_typeahead",
        "displayName": "GO Term or GO ID",
        "vocabulary": _GO_TERMS,
        "initialDisplayValue": "[]",
    }
    param: WDKParameter = type(typeahead).model_validate(body)
    return format_param_info_typed([param])


_TEXT = _sheet(_TEXT_SEARCH)
_LOCATION = _sheet(_LOCATION_SEARCH)
_GO = _go_sheet()
_TEXT_FIELDS = [
    o.value for o in next(i for i in _TEXT if i.name == "text_fields").vocabulary()
]


def _text_values() -> st.SearchStrategy[dict[str, ParamValue]]:
    return st.fixed_dictionaries(
        {
            "text_expression": st.sampled_from(
                ["*reductase", "kinase", "cysteine-rich protein"]
            ).map(lambda text: StringValue(value=text)),
            "text_fields": st.lists(
                st.sampled_from(_TEXT_FIELDS), min_size=1, max_size=4, unique=True
            ).map(lambda picks: MultiPickValue(values=picks)),
        }
    )


def _location_values() -> st.SearchStrategy[dict[str, ParamValue]]:
    return st.fixed_dictionaries(
        {
            "sequenceId": st.sampled_from(
                ["(Example: Pf3D7_04_v3)", "Pf3D7_04_v3"]
            ).map(lambda text: StringValue(value=text)),
            "chromosomeOptional": st.just(SinglePickValue(value="Choose chromosome")),
            "start_point": st.sampled_from([1, 5000]).map(
                lambda n: NumberValue(value=n)
            ),
        }
    )


def _go_values() -> st.SearchStrategy[dict[str, ParamValue]]:
    return st.fixed_dictionaries(
        {
            "go_typeahead": st.lists(
                st.sampled_from([term for term, _, _ in _GO_TERMS]),
                min_size=1,
                max_size=2,
                unique=True,
            ).map(lambda picks: MultiPickValue(values=picks))
        }
    )


def _sheet_fields(
    values: Mapping[str, BoundValue],
) -> dict[str, tuple[str, str, bool, bool]]:
    return {
        name: (held.label, held.display_name, held.placeholder, held.at_default)
        for name, held in values.items()
    }


def _origins(
    values: dict[str, ParamValue], sheet: Sequence[ParameterInfo]
) -> dict[str, dict[str, BoundValue]]:
    bound = bound_values(
        values,
        infos=list(sheet),
        site_supplied=set(),
        request_texts=[_MESSAGE],
        reason="the model's reason",
    )
    empty = Criterion(id="c_one", text="the criterion", search_name="S")
    hydrated = sheet_marked(
        empty.model_copy(update={"resolved_params": bind_values(values, "held", ())}),
        sheet,
    )
    replayed = empty
    for name, value in values.items():
        replayed = criterion_restated(replayed, name, value, sheet=sheet)
    return {
        "bind": bound,
        "hydration": hydrated.resolved_params,
        "replay": replayed.resolved_params,
        "fold": {name: held.carried("c_option") for name, held in bound.items()},
    }


type _Read = dict[str, tuple[str, str, bool, bool, str, str]]


def _read_on_every_path(
    values: dict[str, ParamValue], sheet: Sequence[ParameterInfo]
) -> dict[str, _Read]:
    """Each origin's sheet fields, then who set the value and the fold's carrier."""
    return {
        origin: {
            name: (*fields, held[name].source, held[name].carried_from)
            for name, fields in _sheet_fields(held).items()
        }
        for origin, held in _origins(values, sheet).items()
    }


def _as_held(read: _Read) -> _Read:
    return {name: (*row[:4], "held", "") for name, row in read.items()}


def _as_carried(read: _Read) -> _Read:
    return {name: (*row[:5], "c_option") for name, row in read.items()}


@settings(max_examples=40, deadline=None)
@given(_text_values())
def test_a_text_and_a_pick_read_alike_on_every_path(
    values: dict[str, ParamValue],
) -> None:
    read = _read_on_every_path(values, _TEXT)

    assert read == {
        "bind": read["bind"],
        "hydration": _as_held(read["bind"]),
        "replay": _as_held(read["bind"]),
        "fold": _as_carried(read["bind"]),
    }


@settings(max_examples=20, deadline=None)
@given(_location_values())
def test_a_placeholder_and_a_number_read_alike_on_every_path(
    values: dict[str, ParamValue],
) -> None:
    read = _read_on_every_path(values, _LOCATION)

    assert read == {
        "bind": read["bind"],
        "hydration": _as_held(read["bind"]),
        "replay": _as_held(read["bind"]),
        "fold": _as_carried(read["bind"]),
    }


@settings(max_examples=10, deadline=None)
@given(_go_values())
def test_a_go_term_reads_alike_on_every_path(values: dict[str, ParamValue]) -> None:
    read = _read_on_every_path(values, _GO)

    assert read == {
        "bind": read["bind"],
        "hydration": _as_held(read["bind"]),
        "replay": _as_held(read["bind"]),
        "fold": _as_carried(read["bind"]),
    }


def test_the_sheet_fields_are_the_published_sheets() -> None:
    """One example of each kind, with the fields the sheet gives it."""
    text = _origins(
        {
            "text_expression": StringValue(value="*reductase"),
            "text_fields": MultiPickValue(values=["product"]),
        },
        _TEXT,
    )["replay"]
    location = _origins(
        {
            "sequenceId": StringValue(value="(Example: Pf3D7_04_v3)"),
            "start_point": NumberValue(value=1),
        },
        _LOCATION,
    )["replay"]
    go = _origins({"go_typeahead": MultiPickValue(values=["GO:0007200"])}, _GO)[
        "replay"
    ]

    assert {**_sheet_fields(text), **_sheet_fields(location), **_sheet_fields(go)} == {
        "text_expression": ("", "Text term (use * as wildcard)", False, True),
        "text_fields": ("Product description", "Fields", False, False),
        "sequenceId": ("", "Genomic sequence ID", True, True),
        "start_point": ("", "Start at", False, True),
        "go_typeahead": (
            "phospholipase C-activating G protein-coupled receptor signaling pathway",
            "GO Term or GO ID",
            False,
            False,
        ),
    }
