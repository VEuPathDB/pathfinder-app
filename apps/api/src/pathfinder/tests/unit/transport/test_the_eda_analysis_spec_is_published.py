"""The spec publishes the analysis document an EDA step's parameter holds.

The web validates the document with the schema generated from this component,
so it accepts exactly what the backend's model accepts.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError
from veupathdb.eda import EdaNewAnalysis
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

from pathfinder.main import create_app

_SUBSET = {"subset": {"descriptor": []}, "computations": []}
_REF = "#/components/schemas/{}"


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return create_app(include_dev_routes=False).openapi()


def test_the_analysis_document_is_a_component(spec: dict[str, Any]) -> None:
    schemas = spec["components"]["schemas"]
    assert schemas["EdaNewAnalysis"]["required"] == ["studyId", "displayName"]
    assert schemas["EdaNewAnalysis"]["properties"]["descriptor"] == {
        "$ref": "#/components/schemas/EdaAnalysisDescriptor"
    }
    assert schemas["EdaAnalysisDescriptor"]["properties"]["computations"]["items"] == {
        "$ref": "#/components/schemas/EdaComputation"
    }


def test_a_computation_holds_any_compute_the_site_offers(
    spec: dict[str, Any],
) -> None:
    schemas = spec["components"]["schemas"]
    assert schemas["EdaComputation"]["properties"]["descriptor"] == {
        "$ref": _REF.format("EdaComputeDescriptor")
    }
    assert schemas["EdaComputeDescriptor"]["anyOf"] == [
        {"$ref": _REF.format(name)}
        for name in (
            "EdaDifferentialExpressionDescriptor",
            "EdaPassDescriptor",
            "EdaOtherComputeDescriptor",
        )
    ]
    assert schemas["EdaVisualizationDescriptor"]["anyOf"] == [
        {"$ref": _REF.format(name)}
        for name in ("EdaVolcanoDescriptor", "EdaOtherVisualizationDescriptor")
    ]


def test_a_stored_document_node_keeps_the_keys_it_does_not_model(
    spec: dict[str, Any],
) -> None:
    schemas = spec["components"]["schemas"]
    stored = (
        "EdaAnalysisDescriptor",
        "EdaComputation",
        "EdaPassDescriptor",
        "EdaVisualization",
        "EdaVolcanoConfiguration",
    )
    assert {name: schemas[name].get("additionalProperties") for name in stored} == (
        dict.fromkeys(stored, True)
    )
    assert "additionalProperties" not in schemas["EdaNewAnalysis"]


def test_the_model_takes_an_analysis_the_site_edited() -> None:
    raw = json.loads((FIXTURE_DIR / "analysis_detail_pass_and_de.json").read_text())
    parsed = EdaNewAnalysis.model_validate(raw)
    assert [c.descriptor.type for c in parsed.descriptor.computations] == [
        "pass",
        "differentialexpression",
    ]


@pytest.mark.parametrize(
    ("document", "field"),
    [
        ({"studyId": "DS_45abf80334", "descriptor": _SUBSET}, "displayName"),
        (
            {
                "studyId": "DS_45abf80334",
                "displayName": "Midgut",
                "descriptor": {**_SUBSET, "computations": [42]},
            },
            "descriptor.computations.0",
        ),
    ],
)
def test_the_model_refuses_what_the_web_once_took(
    document: dict[str, Any], field: str
) -> None:
    with pytest.raises(ValidationError) as refused:
        EdaNewAnalysis.model_validate(document)
    assert [".".join(map(str, e["loc"])) for e in refused.value.errors()] == [field]


@pytest.mark.parametrize(
    ("document", "study_id", "filters"),
    [
        ({"studyId": "DS_45abf80334", "displayName": "Midgut"}, "DS_45abf80334", 0),
        ({"studyId": "", "displayName": "Midgut", "descriptor": _SUBSET}, "", 0),
    ],
)
def test_the_model_takes_what_the_web_once_refused(
    document: dict[str, Any], study_id: str, filters: int
) -> None:
    parsed = EdaNewAnalysis.model_validate(document)
    assert (parsed.study_id, len(parsed.descriptor.subset.descriptor)) == (
        study_id,
        filters,
    )
