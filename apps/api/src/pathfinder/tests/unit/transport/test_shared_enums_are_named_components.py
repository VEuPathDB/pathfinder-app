"""Four enums the browser names must reach it as named schema components.

An inline ``Literal`` field generates a nested per-field type in the client, so
the browser hand-writes the union and the two copies drift. Each name below is
a component, and its value set is the wire contract.
"""

import pytest
from assistant_core.platform.types import JSONObject
from pydantic import BaseModel, ConfigDict, Field

from pathfinder.devtools.openapi import _spec_with_stable_overrides


class _NamedSchemas(BaseModel):
    """The component map of an OpenAPI document."""

    model_config = ConfigDict(extra="ignore")

    schemas: dict[str, JSONObject] = Field(default_factory=dict)


class _Spec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    components: _NamedSchemas = Field(default_factory=_NamedSchemas)


class _StringEnum(BaseModel):
    """A component that carries its value set on the wire."""

    model_config = ConfigDict(extra="ignore")

    type: str = ""
    enum: list[str] = Field(default_factory=list)


class _Properties(BaseModel):
    """The fields of one component."""

    model_config = ConfigDict(extra="ignore")

    properties: dict[str, JSONObject] = Field(default_factory=dict)


_EXPECTED_VALUES: dict[str, list[str]] = {
    "ModelProvider": ["openai", "anthropic", "google", "ollama", "mock"],
    "ReasoningEffort": ["none", "low", "medium", "high"],
    "Classification": ["TP", "FP", "FN", "TN"],
    "EnrichmentAnalysisType": [
        "go_function",
        "go_component",
        "go_process",
        "pathway",
        "word",
    ],
}


@pytest.fixture(scope="module")
def schemas() -> dict[str, JSONObject]:
    return _Spec.model_validate(_spec_with_stable_overrides()).components.schemas


@pytest.mark.parametrize("name", sorted(_EXPECTED_VALUES))
def test_the_enum_is_a_named_string_component(
    name: str, schemas: dict[str, JSONObject]
) -> None:
    assert _StringEnum.model_validate(schemas[name]).type == "string"


@pytest.mark.parametrize("name", sorted(_EXPECTED_VALUES))
def test_the_enum_carries_its_wire_values(
    name: str, schemas: dict[str, JSONObject]
) -> None:
    assert _StringEnum.model_validate(schemas[name]).enum == _EXPECTED_VALUES[name]


@pytest.mark.parametrize(
    ("schema_name", "field_name", "expected"),
    [
        (
            "ModelListResponse",
            "defaultProvider",
            {"$ref": "#/components/schemas/ModelProvider"},
        ),
        (
            "ModelCatalogEntryResponse",
            "provider",
            {"$ref": "#/components/schemas/ModelProvider"},
        ),
        (
            "PhaseTierConfig",
            "reasoningEffort",
            {"$ref": "#/components/schemas/ReasoningEffort"},
        ),
        (
            "ClassifiedRecord",
            "classification",
            {
                "anyOf": [
                    {"$ref": "#/components/schemas/Classification"},
                    {"type": "null"},
                ]
            },
        ),
        (
            "EnrichmentResult",
            "analysisType",
            {"$ref": "#/components/schemas/EnrichmentAnalysisType"},
        ),
    ],
)
def test_the_field_references_the_component(
    schema_name: str,
    field_name: str,
    expected: JSONObject,
    schemas: dict[str, JSONObject],
) -> None:
    fields = _Properties.model_validate(schemas[schema_name]).properties
    assert fields[field_name] == expected


def test_the_enrichment_chunk_carries_typed_results(
    schemas: dict[str, JSONObject],
) -> None:
    chunk = _Properties.model_validate(schemas["EnrichmentResultsChunk"])
    results = chunk.properties["results"]

    assert results["type"] == "array"
    assert results["items"] == {"$ref": "#/components/schemas/EnrichmentResult"}
