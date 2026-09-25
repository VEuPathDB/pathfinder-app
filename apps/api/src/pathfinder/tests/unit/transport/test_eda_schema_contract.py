"""What the EDA routes promise: a model omits no field it declares."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from pathfinder.transport.http.schemas.eda import (
    ConversationEdaResponse,
    EdaAnalysisPatchResponse,
    EdaExportStepAction,
    EdaStudyListResponse,
    EdaStudySummaryResponse,
    EdaVizPointResponse,
    EdaVizRequest,
    EdaVizResponse,
)

_RESPONSES = [
    ConversationEdaResponse,
    EdaAnalysisPatchResponse,
    EdaStudyListResponse,
    EdaStudySummaryResponse,
    EdaVizPointResponse,
    EdaVizResponse,
]


@pytest.mark.parametrize("model", _RESPONSES, ids=lambda m: m.__name__)
def test_a_response_model_requires_every_field_it_declares(
    model: type[BaseModel],
) -> None:
    """The builder fills every field, so a consumer never defaults one."""
    schema = model.model_json_schema(by_alias=True)
    assert schema["required"] == list(schema["properties"])


def test_a_point_may_carry_no_p_value_and_still_names_the_key() -> None:
    schema = EdaVizPointResponse.model_json_schema(by_alias=True)
    assert schema["properties"]["pValue"]["anyOf"] == [
        {"type": "number"},
        {"type": "null"},
    ]
    assert "pValue" in schema["required"]


def test_the_volcano_request_names_no_cut_and_no_dataset() -> None:
    """The cut and the dataset are the bound analysis's, so a client sends neither."""
    schema = EdaVizRequest.model_json_schema(by_alias=True)
    assert set(schema["properties"]) == {"chart"}


def test_an_export_names_its_source_and_no_cut() -> None:
    """A volcano export writes the cut the analysis stores."""
    schema = EdaExportStepAction.model_json_schema(by_alias=True)
    assert (set(schema["properties"]), schema["properties"]["source"]["enum"]) == (
        {"action", "source"},
        ["volcano", "subset"],
    )
