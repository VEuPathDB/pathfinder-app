"""A filter value the model writes as an object reaches the tool server as JSON
text and binds in the shape its facet takes."""

from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter
from veupathdb.domain.parameters import FilterValue, WDKFilterOntologyTerm
from veupathdb.wdk import WDKFilterParam
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.agents.frame import _FRAME_INSTRUCTIONS
from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone import frame_spec
from pathfinder.ai.tools.standalone._frame_proposals import ParamProposals
from pathfinder.tests.unit.ai.tools.test_frame_spec import bind, serve_search

_ADAPTER: TypeAdapter[ParamProposals] = TypeAdapter(ParamProposals)

_VARIANT_STATS = "gene_variant_stats"
_MAF_AT_MOST: dict[str, object] = {
    "filters": [{"field": "max_minor_allele_frequency", "value": {"max": 0.05}}]
}
# Three of the facets plasmodb publishes for GenesByVariantCharacteristics.
_VARIANT_STATS_PARAM = WDKFilterParam(
    name=_VARIANT_STATS,
    display_name="Variant statistics",
    ontology=[
        WDKFilterOntologyTerm(term="variant_burden", display="Variant burden"),
        WDKFilterOntologyTerm(term="variant_consequence", display="Consequence"),
        WDKFilterOntologyTerm(term="variant_frequency", display="Allele frequency"),
        WDKFilterOntologyTerm(
            term="max_minor_allele_frequency",
            display="Highest minor allele frequency",
            parent="variant_frequency",
            type="number",
            is_range=True,
        ),
        WDKFilterOntologyTerm(
            term="variants_per_kb",
            display="Variants per kb",
            parent="variant_burden",
            type="number",
            is_range=True,
        ),
        WDKFilterOntologyTerm(
            term="most_severe_impact",
            display="Most severe impact",
            parent="variant_consequence",
            type="string",
        ),
    ],
    values={"most_severe_impact": ["MODERATE", "MODIFIER", "HIGH", "LOW"]},
)


def test_a_mapping_is_carried_as_its_json_text() -> None:
    assert _ADAPTER.validate_python({_VARIANT_STATS: _MAF_AT_MOST}) == {
        _VARIANT_STATS: json.dumps(_MAF_AT_MOST)
    }


async def test_an_object_filter_value_binds_in_the_shape_its_facet_takes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    st = AgentToolState()
    serve_search(
        monkeypatch, lambda _context: format_param_info_typed([_VARIANT_STATS_PARAM])
    )
    proposals = _ADAPTER.validate_python({_VARIANT_STATS: _MAF_AT_MOST})

    await bind(st, "GenesByVariantCharacteristics", proposals, text="rare variants")

    bound = st.operational_spec_draft.criteria[0].resolved_params[_VARIANT_STATS]
    assert isinstance(bound, FilterValue)
    assert json.loads(bound.to_wire()) == {
        "filters": [
            {
                "field": "max_minor_allele_frequency",
                "type": "number",
                "isRange": True,
                "includeUnknown": False,
                "value": {"max": 0.05},
            }
        ]
    }


def test_the_filter_sheet_states_the_member_and_the_range_form() -> None:
    [info] = format_param_info_typed([_VARIANT_STATS_PARAM])

    assert '"value": ["<member>", "..."]' in info.value_format
    assert '"value": {"min": <n>, "max": <n>}' in info.value_format
    assert "<range facet><=<n>" in info.value_format
    assert "<member facet>=<m1>,<m2>" in info.value_format


@pytest.mark.parametrize(
    "guidance",
    [_FRAME_INSTRUCTIONS, frame_spec.set_criterion.__doc__ or ""],
    ids=["frame_instructions", "set_criterion_description"],
)
def test_the_guidance_names_the_member_and_the_range_shorthand(guidance: str) -> None:
    assert '"<member facet>=<v1>,<v2>"' in guidance
    assert '"<range facet><=<n>"' in guidance
    assert '"<range facet>=<lo>..<hi>"' in guidance
    assert "marks is_range or of type date" in " ".join(guidance.split())
