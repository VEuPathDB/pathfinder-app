"""Four names in ``@strategist/shared`` collide with ``wdk-client`` and mean
something else. The browser is a client for Strategist, not for WDK.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_TYPES_TS = (
    Path(__file__).resolve().parents[6] / "packages" / "shared-ts" / "src" / "types.ts"
)

# What each name is in Strategist: an alias of a Strategist response type.
_STRATEGIST_SOURCE = {
    "Search": "SearchResponse",
    "RecordType": "RecordTypeResponse",
    "Step": "StepResponse",
    "Strategy": "ConversationResponse",
}

# The field that would mark the wdk-client type of the same name.
_WDK_MARKER = {
    "Search": "paramNames",
    "RecordType": "attributes",
    "Step": "searchConfig",
    "Strategy": "stepTree",
}


def _declaration(name: str) -> str:
    source = _TYPES_TS.read_text()
    match = re.search(
        rf"^export type {name} = (.+?);$", source, re.MULTILINE | re.DOTALL
    )
    assert match is not None, f"{name} is not declared in {_TYPES_TS}"
    return match.group(1)


@pytest.mark.parametrize("name", sorted(_STRATEGIST_SOURCE))
def test_wdk_map_008_each_name_aliases_a_strategist_response(name: str) -> None:
    assert _STRATEGIST_SOURCE[name] in _declaration(name)


@pytest.mark.parametrize("name", sorted(_WDK_MARKER))
def test_wdk_map_008_no_name_carries_the_wdk_shape(name: str) -> None:
    # A reviewer reading `Step.id` must not reason about it as a WDK step id.
    assert _WDK_MARKER[name] not in _declaration(name)


def test_wdk_map_008_a_strategy_inlines_its_steps_instead_of_a_tree() -> None:
    declaration = _declaration("Strategy")

    assert "steps: StepResponse[]" in declaration
    assert "stepTree" not in declaration
