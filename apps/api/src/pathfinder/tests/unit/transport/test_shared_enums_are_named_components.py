"""Four enums the browser names must reach it as named schema components.

An inline ``Literal`` field generates a nested per-field type in the client, so
the browser hand-writes the union and the two copies drift. Each name below is
a component, and its value set is the wire contract.
"""

from typing import Any

import pytest

from pathfinder.devtools.openapi import _spec_with_stable_overrides

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
def schemas() -> dict[str, Any]:
    components: dict[str, Any] = _spec_with_stable_overrides()["components"]
    named: dict[str, Any] = components["schemas"]
    return named


@pytest.mark.parametrize("name", sorted(_EXPECTED_VALUES))
def test_the_enum_is_a_named_string_component(
    name: str, schemas: dict[str, Any]
) -> None:
    assert schemas[name]["type"] == "string"


@pytest.mark.parametrize("name", sorted(_EXPECTED_VALUES))
def test_the_enum_carries_its_wire_values(name: str, schemas: dict[str, Any]) -> None:
    assert schemas[name]["enum"] == _EXPECTED_VALUES[name]


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
    expected: dict[str, Any],
    schemas: dict[str, Any],
) -> None:
    assert schemas[schema_name]["properties"][field_name] == expected


def test_the_enrichment_chunk_carries_typed_results() -> None:
    schemas = _spec_with_stable_overrides()["components"]["schemas"]
    results = schemas["EnrichmentResultsChunk"]["properties"]["results"]

    assert results["type"] == "array"
    assert results["items"] == {"$ref": "#/components/schemas/EnrichmentResult"}
