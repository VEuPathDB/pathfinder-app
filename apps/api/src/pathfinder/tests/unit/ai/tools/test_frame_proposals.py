"""Reading a proposal: coercion, unknown names, unmatched values, derivations."""

from __future__ import annotations

from typing import NamedTuple

import pytest
from pydantic import TypeAdapter
from pydantic import ValidationError as PydanticValidationError
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters.wdk_vocab import VocabOption, WDKVocabTerm
from veupathdb.domain.search import SearchContext
from veupathdb.wdk.wdk_parameters import (
    WDKEnumParam,
    WDKParameter,
    WDKStringParam,
)
from veupathdb_mcp.catalog import (
    ResolvedParams,
    UnknownParameterError,
    format_param_info_typed,
)

from pathfinder.ai.agents.state import AgentToolState, SearchOverview
from pathfinder.ai.tools.standalone import frame_spec
from pathfinder.ai.tools.standalone._frame_proposals import (
    ParamProposals,
    coerce_proposals,
)
from pathfinder.ai.tools.standalone.frame_spec import SetCriterionResult
from pathfinder.tests._support.catalog_builders import ParamsAt
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    KINASE_PARAMS,
    Proposals,
    bind,
    genes_by_text,
    param_info,
    serve_search,
)

_ADAPTER: TypeAdapter[ParamProposals] = TypeAdapter(ParamProposals)


def test_numbers_and_json_lists_are_read() -> None:
    assert coerce_proposals(
        {"fold_change": 2, "adj_p_value": 1e-8, "organism": '["Plasmodium"]', "x": None}
    ) == {
        "fold_change": "2",
        "adj_p_value": "1e-08",
        "organism": ["Plasmodium"],
        "x": None,
    }


def test_a_string_and_a_real_list_are_unchanged() -> None:
    assert coerce_proposals(
        {"organism": "Plasmodium falciparum 3D7", "samples": ["20 Hour"]}
    ) == {"organism": "Plasmodium falciparum 3D7", "samples": ["20 Hour"]}


def test_a_list_of_numbers_becomes_a_list_of_strings() -> None:
    assert coerce_proposals({"hours": [20, 21]}) == {"hours": ["20", "21"]}
    assert coerce_proposals({"hours": "[20, 21]"}) == {"hours": ["20", "21"]}


def test_a_boolean_is_read_as_its_json_word() -> None:
    # A yes/no parameter has a vocabulary, so a boolean has to reach it as a
    # value rather than fail the schema.
    assert coerce_proposals({"is_syntenic": True, "is_pseudo": False}) == {
        "is_syntenic": "true",
        "is_pseudo": "false",
    }


def test_a_nested_object_is_refused_naming_the_parameter() -> None:
    # A filter value travels as a JSON string, never as a bare object.
    with pytest.raises(ValueError, match="ngsSnp_strain_meta"):
        coerce_proposals({"ngsSnp_strain_meta": {"filters": []}})


def test_the_annotation_reports_the_offending_parameter() -> None:
    with pytest.raises(PydanticValidationError, match="ngsSnp_strain_meta"):
        _ADAPTER.validate_python({"ngsSnp_strain_meta": {"filters": []}})


def test_bracketed_text_that_is_not_json_stays_text() -> None:
    assert coerce_proposals({"text_expression": "[unnamed]"}) == {
        "text_expression": "[unnamed]"
    }


def test_a_non_mapping_passes_through_for_pydantic_to_reject() -> None:
    assert coerce_proposals("not a mapping") == "not a mapping"


def test_the_annotation_validates_and_has_a_json_schema() -> None:
    # The annotation becomes the tool schema the model reads, so it has to
    # stay JSON-schema-friendly.
    assert _ADAPTER.validate_python({"fold_change": 2}) == {"fold_change": "2"}
    assert _ADAPTER.json_schema()["type"] == "object"


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
        _one("domain_typeahead", "single-pick-vocabulary", _PFAM),
        "kinase domain genes",
    ),
    "GenesBySharedDomain": _Search(
        _one(
            "domain_typeahead",
            "single-pick-vocabulary",
            _options("PF00069 : Pkinase", "PF00069 : Pkinase_C"),
        ),
        "kinase domain genes",
    ),
    "GenesByExpressionPercentile": _Search(
        _percentile(), "top 10 percent by expression"
    ),
    "GenesByOptionalPercentile": _Search(
        _percentile(required=False), "top 10 percent by expression"
    ),
    "GenesByOrthologPattern": _Search(
        lambda _c: format_param_info_typed(_PHYLETIC), _PHYLETIC_TEXT, _PHYLETIC
    ),
    "GenesByEcNumber": _Search(
        lambda _c: format_param_info_typed(_EC),
        "protein kinases",
        _EC,
        {"radio-params": ["ec_number_pattern", "ec_wildcard"]},
    ),
    "GenesByGoTerm": _Search(
        lambda _c: format_param_info_typed(_GO),
        "protein kinase activity",
        _GO,
        {"radio-params": ["go_typeahead", "go_term"]},
    ),
}


def serve_for(monkeypatch: pytest.MonkeyPatch, search: str) -> list[SearchContext]:
    entry = SEARCHES[search]
    return serve_search(
        monkeypatch, entry.at, catalog=entry.catalog, properties=entry.properties
    )


async def propose(
    state: AgentToolState, search: str, params: Proposals
) -> SetCriterionResult:
    return await bind(state, search, params, text=SEARCHES[search].text)


_ORGANISM_MISS = {**KINASE_PARAMS, "text_search_organism": ["Plasmodium falciprum 3D7"]}
_PF_SUBSTRING = {**KINASE_PARAMS, "text_search_organism": ["falciparum"]}
_BOGUS_NAME = {**KINASE_PARAMS, "totally_bogus_name": None}
PHYLETIC_ORGANISM: Proposals = {"organism": ["Pf3D7"]}

_REFUSALS: list[tuple[str, Proposals, tuple[str, ...]]] = [
    (
        "GenesByText",
        _ORGANISM_MISS,
        ("text_search_organism", "Plasmodium falciparum 3D7"),
    ),
    # "falciparum" reads as either organism under substring matching, so the
    # binding it would produce is decided by vocabulary order.
    ("GenesByText", _PF_SUBSTRING, ()),
    ("GenesByText", _BOGUS_NAME, ("totally_bogus_name", "text_expression")),
    (
        "GenesByOrthologs",
        _ADAPTER.validate_python({"is_syntenic": False}),
        ("'false'", "'no'"),
    ),
    (
        "GenesBySharedDomain",
        {"domain_typeahead": "PF00069"},
        ("share the accession", "PF00069 : Pkinase_C"),
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
        ("at least one species or clade", "included_species"),
    ),
    (
        "GenesByOrthologPattern",
        dict(PHYLETIC_ORGANISM),
        ("at least one species or clade",),
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
        ("ec_number_pattern default 2.7.11.1 would still contribute",),
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
async def test_the_nearest_entries_lead_with_the_ones_the_value_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_for(monkeypatch, "GenesByInterproDomain")

    with pytest.raises(ModelRetry) as info:
        await propose(
            AgentToolState(), "GenesByInterproDomain", {"domain_typeahead": "PF0006"}
        )

    message = str(info.value)
    assert message.index("PF00069 : Pkinase") < message.index("PF00569 : ZZ")


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
    monkeypatch.setattr(frame_spec, "resolve_params_with_intent", _resolve)

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


_PASSTHROUGH: list[tuple[str, str | list[str] | None, dict[str, object]]] = [
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
    proposed: str | list[str] | None,
    expected: dict[str, object],
) -> None:
    # A multi-pick slot answered with a list stays a list: the codec encodes it
    # at the wire, which is the only place that wants a string.
    captured: dict[str, object] = {}

    async def _resolve(**kwargs: object) -> ResolvedParams:
        captured.update(kwargs)
        return ResolvedParams(params={}, open_slots=[])

    serve_search(monkeypatch, lambda _context: [param_info("samples", param_type)])
    monkeypatch.setattr(frame_spec, "resolve_params_with_intent", _resolve)

    await bind(AgentToolState(), "GenesByMicroarray", {"samples": proposed})

    assert captured["overrides"] == expected
