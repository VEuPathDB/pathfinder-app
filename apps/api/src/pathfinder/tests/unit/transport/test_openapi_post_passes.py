from typing import Any

import pytest

from pathfinder.main import create_app


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return create_app(include_dev_routes=False).openapi()


def _null_valued_paths(node: Any, path: str = "") -> list[str]:
    if isinstance(node, dict):
        found = [f"{path}/{k}" for k, v in node.items() if v is None]
        for key, value in node.items():
            found.extend(_null_valued_paths(value, f"{path}/{key}"))
        return found
    if isinstance(node, list):
        return [
            hit
            for index, item in enumerate(node)
            for hit in _null_valued_paths(item, f"{path}[{index}]")
        ]
    return []


def test_anchored_components_are_present(spec: dict[str, Any]) -> None:
    schemas = spec["components"]["schemas"]
    assert {
        "ProblemDetail",
        "Experiment",
        "StreamPartsSchemaIndex",
        "GraphCleared",
    } <= set(schemas)


def test_the_spec_carries_no_null_values(spec: dict[str, Any]) -> None:
    assert _null_valued_paths(spec["components"]["schemas"]) == []


def test_anchored_payloads_carry_their_computed_fields(spec: dict[str, Any]) -> None:
    frame = spec["components"]["schemas"]["FrameSection"]["properties"]
    assert {"criteriaCount", "readyToBuild", "needsUser", "structureRender"} <= set(
        frame
    )
