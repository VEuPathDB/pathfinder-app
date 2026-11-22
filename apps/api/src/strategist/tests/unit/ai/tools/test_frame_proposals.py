"""Reading a proposal: unknown names, unmatched values, derivations."""

from __future__ import annotations

from typing import NamedTuple

import pytest
from pydantic import JsonValue
from pydantic_ai import ModelRetry
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import VocabOption, WDKVocabTerm
from veupathdb.wdk import (
    WDKEnumParam,
    WDKParameter,
    WDKStringParam,
)
from veupathdb_mcp.catalog import (
    ResolvedParams,
    UnknownParameterError,
)

from strategist.ai.agents.state import AgentToolState, SearchOverview
from strategist.ai.tools.standalone import _frame_proposals
from strategist.ai.tools.standalone._frame_result import SetCriterionResult
from strategist.tests._support.catalog_builders import ParamsAt
from strategist.tests.unit.ai.tools.test_frame_spec import (
    KINASE_PARAMS,
    Proposals,
    bind,
    genes_by_text,
    no_sheet,
    param_info,
    serve_search,
)


def _options(*values: str) -> list[VocabOption]:
    return [VocabOption(value=v, display=v) for v in values]


def _one(name: str, param_type: str, options: list[VocabOption]) -> ParamsAt:
    return lambda _context: [param_info(name, param_type, vocab_leaves=options)]


def _percentile(*, required: bool = True) -> ParamsAt:
    return lambda _context: [
        param_info(
            "min_expression_percentile",
            required=required,
            is_number=True,
            default_value="80",
        )
    ]


def _enum(
    name: str,
    *terms: tuple[str, str, None],
    param_type: str = "multi-pick-vocabulary",
    **fields: object,
) -> WDKEnumParam:
    return WDKEnumParam.model_validate(
        {
            "name": name,
            "type": param_type,
            "vocabulary": [WDKVocabTerm(t) for t in terms],
            **fields,
        }
    )


_PFAM = _options(
    "PF00069 : Pkinase",
    "PF00569 : ZZ",
    "PF00169 : PH",
    "PF00560 : LRR_1",
    "PF00006 : ATP-synt_ab",
)
_SHARED = _options("PF00069 : Pkinase", "PF00069 : Pkinase_C")


def _typeahead(options: list[VocabOption]) -> WDKEnumParam:
    return _enum(
        "domain_typeahead",
        *[(o.value, o.display, None) for o in options],
        param_type="single-pick-vocabulary",
        display_type="typeAhead",
    )


_PHYLETIC: list[WDKParameter] = [
    WDKStringParam(
        name="profile_pattern", is_visible=False, initial_display_value="hsap=1T"
    ),
    WDKStringParam(name="included_species", allow_empty_value=True),
    WDKStringParam(name="excluded_species", allow_empty_value=True),
    _enum("organism", ("Pf3D7", "P. falciparum 3D7", None)),
    _enum(
        "phyletic_term_map",
        ("ALL", "Root", None),
        ("EUKA", "Eukaryota", None),
        ("MAMM", "Mammalia", None),
        ("hsap", "Homo sapiens REF", None),
        ("mmus", "Mus musculus", None),
        ("pfal", "Plasmodium falciparum 3D7", None),
    ),
    _enum(
        "phyletic_indent_map",
        ("EUKA", "1", None),
        ("MAMM", "2", None),
        ("hsap", "3", None),
        ("mmus", "3", None),
        ("pfal", "2", None),
    ),
]
_EC: list[WDKParameter] = [
    _enum(
        "ec_number_pattern",
        *[(v, v, None) for v in ("2.7.-.-", "2.7.11.1", "3.4.21.-")],
        param_type="single-pick-vocabulary",
        initial_display_value="2.7.11.1",
    ),
    WDKStringParam(name="ec_wildcard", initial_display_value="N/A"),
]
_GO_TERM = "GO:0004672 : protein kinase activity"
_GO: list[WDKParameter] = [
    _enum(
        "go_typeahead",
        (_GO_TERM, _GO_TERM, None),
        display_type="typeAhead",
        initial_display_value="[]",
    ),
    WDKStringParam(name="go_term", initial_display_value="N/A"),
]


class _Search(NamedTuple):
    at: ParamsAt
    text: str
    catalog: list[WDKParameter] | None = None
    properties: dict[str, list[str]] | None = None


_PHYLETIC_TEXT = "present in P. falciparum, absent from mammals"
SEARCHES: dict[str, _Search] = {
    "GenesByText": _Search(genes_by_text, "kinases"),
    "GenesByOrthologs": _Search(
        _one("is_syntenic", "single-pick-vocabulary", _options("yes", "no")),
        "non-syntenic orthologs",
    ),
    "GenesByInterproDomain": _Search(
        no_sheet,
        "kinase domain genes",
        [_typeahead(_PFAM)],
    ),
    "GenesBySharedDomain": _Search(
        no_sheet,
        "kinase domain genes",
        [_typeahead(_SHARED)],
    ),
    "GenesByExpressionPercentile": _Search(
        _percentile(), "top 10 percent by expression"
    ),
    "GenesByOptionalPercentile": _Search(
        _percentile(required=False), "top 10 percent by expression"
    ),
    "GenesByOrthologPattern": _Search(no_sheet, _PHYLETIC_TEXT, _PHYLETIC),
    "GenesByEcNumber": _Search(
        no_sheet,
        "protein kinases",
        _EC,
        {"radio-params": ["ec_number_pattern", "ec_wildcard"]},
    ),
    "GenesByGoTerm": _Search(
        no_sheet,
        "protein kinase activity",
        _GO,
        {"radio-params": ["go_typeahead", "go_term"]},
    ),
}


def serve_for(monkeypatch: pytest.MonkeyPatch, search: str) -> list[SearchContext]:
    entry = SEARCHES[search]
    return serve_search(
        monkeypatch,
        entry.at,
        catalog=entry.catalog,
        properties=entry.properties,
        declared=entry.catalog or (),
    )


async def propose(
    state: AgentToolState, search: str, params: Proposals
) -> SetCriterionResult:
    return await bind(state, search, params, text=SEARCHES[search].text)


_ORGANISM_MISS: Proposals = {
    **KINASE_PARAMS,
    "text_search_organism": ["Plasmodium falciprum 3D7"],
}
_PF_SUBSTRING: Proposals = {**KINASE_PARAMS, "text_search_organism": ["falciparum"]}
_BOGUS_NAME: Proposals = {**KINASE_PARAMS, "totally_bogus_name": None}
PHYLETIC_ORGANISM: Proposals = {"organism": ["Pf3D7"]}

_REFUSALS: list[tuple[str, Proposals, tuple[str, ...]]] = [
    (
        "GenesByText",
        _ORGANISM_MISS,
        (
            "text_search_organism has no entry 'Plasmodium falciprum 3D7'",
            "Candidates: P. falciparum 3D7 (Plasmodium falciparum 3D7)",
        ),
    ),
    # "falciparum" reads as either organism under substring matching, so the
    # binding it would produce is decided by vocabulary order.
    ("GenesByText", _PF_SUBSTRING, ()),
    ("GenesByText", _BOGUS_NAME, ("totally_bogus_name", "text_expression")),
    (
        "GenesByOrthologs",
        {"is_syntenic": False},
        ("is_syntenic takes one of 'yes', 'no'", "it read False"),
    ),
    (
        "GenesBySharedDomain",
        {"domain_typeahead": "PF00069"},
        (
            "domain_typeahead has no entry 'PF00069'",
            "Candidates: PF00069 : Pkinase, PF00069 : Pkinase_C",
        ),
    ),
    (
        "GenesByExpressionPercentile",
        {"min_expression_percentile": None},
        ("min_expression_percentile", "Pass the stated value"),
    ),
    ("GenesByOptionalPercentile", {}, ("min_expression_percentile",)),
    (
        "GenesByOrthologPattern",
        {**PHYLETIC_ORGANISM, "included_species": "Plasmodium falciparum"},
        ("Plasmodium falciparum 3D7", "included_species"),
    ),
    (
        "GenesByOrthologPattern",
        {**PHYLETIC_ORGANISM, "included_species": "Plasmodium"},
        ("A genus or common name is not a node", "lookup_phyletic_codes(query)"),
    ),
    (
        "GenesByOrthologPattern",
        {
            **PHYLETIC_ORGANISM,
            "included_species": "pfal, hsap",
            "excluded_species": "hsap",
        },
        ("hsap",),
    ),
    (
        "GenesByOrthologPattern",
        {**PHYLETIC_ORGANISM, "included_species": None, "excluded_species": None},
        ("select no species", "included_species"),
    ),
    (
        "GenesByOrthologPattern",
        dict(PHYLETIC_ORGANISM),
        ("select no species",),
    ),
    (
        "GenesByOrthologPattern",
        {**PHYLETIC_ORGANISM, "profile_pattern": "%pfal:Y%"},
        ("profile_pattern",),
    ),
    (
        "GenesByEcNumber",
        {"ec_number_pattern": None, "ec_wildcard": "2.7.*"},
        ("2.7.-.-", "ec_number_pattern", "2.7.11.1"),
    ),
    (
        "GenesByEcNumber",
        {"ec_number_pattern": None, "ec_wildcard": "*kinase*"},
        ("get_parameter_options", "N/A"),
    ),
    (
        "GenesByEcNumber",
        {"ec_number_pattern": None, "ec_wildcard": "*protease*"},
        ('ec_number_pattern default "2.7.11.1" would still contribute',),
    ),
]


@pytest.mark.parametrize(("search", "params", "fragments"), _REFUSALS)
@pytest.mark.asyncio
async def test_a_refused_proposal_names_what_is_wrong(
    monkeypatch: pytest.MonkeyPatch,
    search: str,
    params: Proposals,
    fragments: tuple[str, ...],
) -> None:
    serve_for(monkeypatch, search)
    st = AgentToolState()

    with pytest.raises(ModelRetry) as info:
        await propose(st, search, params)

    message = str(info.value)
    for fragment in fragments:
        assert fragment in message
    assert st.operational_spec_draft.criteria == []


@pytest.mark.asyncio
async def test_the_retry_does_not_quote_a_default_the_search_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The GO vocabulary half publishes an empty list, which the search that
    # published it refuses, so there is no value to say would contribute.
    serve_for(monkeypatch, "GenesByGoTerm")

    with pytest.raises(ModelRetry) as info:
        await propose(
            AgentToolState(),
            "GenesByGoTerm",
            {"go_typeahead": None, "go_term": "*kinase*"},
        )

    message = str(info.value)
    assert "go_typeahead cannot be left empty" in message
    assert "default" not in message
    assert _GO_TERM in message
    assert "query=[<every phrasing of the concept>]" in message
    assert "list the entries a phrase matched" in message


@pytest.mark.asyncio
async def test_a_search_with_no_species_list_derives_no_pattern(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # One cached definition read serves every derivation of the call.
    read = serve_search(monkeypatch, genes_by_text, catalog=_PHYLETIC)
    registered = AgentToolState()
    registered.register_search(
        "GenesByText",
        SearchOverview(
            search_name="GenesByText",
            display_name="GenesByText",
            record_type="transcript",
            description="",
            parameter_names=[],
            required_params=[],
        ),
    )

    result = await propose(registered, "GenesByText", dict(KINASE_PARAMS))

    assert result.resolved_params["text_expression"] == "kinase"
    assert "profile_pattern" not in result.resolved_params
    assert [c.search_name for c in read] == ["GenesByText"]


@pytest.mark.asyncio
async def test_an_unknown_parameter_error_becomes_a_retry_listing_the_real_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The DAG's own name check is the backstop, and its retry carries the
    # names, so it must not send the model back for the sheet.
    st = AgentToolState()

    async def _resolve(**_kw: object) -> ResolvedParams:
        raise UnknownParameterError(["min_percentile"], ["min_expression_percentile"])

    serve_for(monkeypatch, "GenesByOptionalPercentile")
    monkeypatch.setattr(_frame_proposals, "resolve_params_with_intent", _resolve)

    with pytest.raises(ModelRetry) as exc:
        await propose(
            st, "GenesByOptionalPercentile", {"min_expression_percentile": "90"}
        )

    message = str(exc.value)
    assert "min_percentile" in message
    assert "min_expression_percentile" in message
    assert "do not request the sheet again" in message
    assert "get_search_overview" not in message
    assert st.operational_spec_draft.criteria == []


_PASSTHROUGH: list[tuple[str, JsonValue, dict[str, object]]] = [
    (
        "multi-pick-vocabulary",
        ["20 Hour", "21 Hour"],
        {"samples": ["20 Hour", "21 Hour"]},
    ),
    ("string", "Plasmodium falciparum 3D7", {"samples": "Plasmodium falciparum 3D7"}),
    ("string", None, {}),
]


@pytest.mark.parametrize(("param_type", "proposed", "expected"), _PASSTHROUGH)
@pytest.mark.asyncio
async def test_a_proposal_reaches_the_resolver_as_the_model_wrote_it(
    monkeypatch: pytest.MonkeyPatch,
    param_type: str,
    proposed: JsonValue,
    expected: dict[str, object],
) -> None:
    # A multi-pick slot answered with a list stays a list: the codec encodes it
    # at the wire, which is the only place that wants a string.
    captured: dict[str, object] = {}

    async def _resolve(**kwargs: object) -> ResolvedParams:
        captured.update(kwargs)
        return ResolvedParams(params={}, open_slots=[])

    serve_search(monkeypatch, lambda _context: [param_info("samples", param_type)])
    monkeypatch.setattr(_frame_proposals, "resolve_params_with_intent", _resolve)

    await bind(AgentToolState(), "GenesByMicroarray", {"samples": proposed})

    assert captured["stated"] == expected
