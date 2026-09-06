from __future__ import annotations

import pytest
from pydantic import BaseModel, TypeAdapter
from veupathdb.domain.parameters.values import MultiPickValue, StringValue
from veupathdb.domain.search import SearchContext
from veupathdb.errors import ValidationError
from veupathdb.wdk.factory import get_wdk_client
from veupathdb.wdk.wdk_models import WDKSearchResponse
from veupathdb_mcp.catalog.param_adapters import adapt_param_specs_from_search
from veupathdb_mcp.catalog.param_validation import validate_parameters
from veupathdb_mcp.catalog.validation_callbacks import make_validation_callbacks

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]


async def _fetch_response() -> WDKSearchResponse:
    client = get_wdk_client("plasmodb")
    return await client.get_search_details_with_params(
        "transcript", "GenesByText", context={}
    )


async def test_layer1_wdk_parse_preserves_allow_empty_false(
    wdk_session: None,
) -> None:
    del wdk_session
    response = await _fetch_response()
    params = {p.name: p for p in (response.search_data.parameters or [])}
    assert params["text_expression"].allow_empty_value is False


async def test_layer2_adapter_preserves_allow_empty_false(
    wdk_session: None,
) -> None:
    del wdk_session
    response = await _fetch_response()
    specs = adapt_param_specs_from_search(response.search_data)
    assert specs["text_expression"].allow_empty_value is False


class _RefusedParam(BaseModel):
    param: str
    messages: list[str]


async def test_layer3_validate_parameters_relays_wdks_refusal(
    wdk_session: None,
) -> None:
    del wdk_session
    with pytest.raises(ValidationError) as raised:
        await validate_parameters(
            SearchContext("plasmodb", "transcript", "GenesByText"),
            parameters={},
            callbacks=make_validation_callbacks("plasmodb"),
        )

    # WDK judged the values while answering, and its bundle names every empty
    # visible required parameter by key; only the hidden one is filled here.
    rows = TypeAdapter(list[_RefusedParam]).validate_python(raised.value.errors)
    assert {row.param for row in rows} == {
        "text_expression",
        "text_fields",
        "text_search_organism",
    }
    assert all(row.messages == ["Cannot be empty."] for row in rows)


async def test_document_type_is_hidden_required_with_fixed_default(
    wdk_session: None,
) -> None:
    del wdk_session
    response = await _fetch_response()
    specs = adapt_param_specs_from_search(response.search_data)
    doc = specs["document_type"]
    assert doc.is_visible is False
    assert doc.allow_empty_value is False
    assert doc.initial_display_value == "gene"


async def test_validate_parameters_autofills_hidden_document_type(
    wdk_session: None,
) -> None:
    # The model supplies only the VISIBLE required params (it can't see the
    # hidden document_type). validate_parameters must auto-fill document_type
    # rather than reject — the contradiction that spiralled create_plan.
    del wdk_session
    result = await validate_parameters(
        SearchContext("plasmodb", "transcript", "GenesByText"),
        parameters={
            "text_expression": StringValue(value="kinase"),
            "text_fields": MultiPickValue(values=["product"]),
            "text_search_organism": MultiPickValue(
                values=["Plasmodium falciparum 3D7"]
            ),
        },
        callbacks=make_validation_callbacks("plasmodb"),
    )
    assert "document_type" in result.params
    assert result.params["document_type"].to_decoded() == "gene"
    # The caller never stated it, so the walk discloses it.
    assert "document_type" in result.substituted
