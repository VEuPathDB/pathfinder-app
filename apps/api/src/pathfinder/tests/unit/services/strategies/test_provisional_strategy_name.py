"""A strategy pushed before its thread has a title is named after the request.

The web names an untitled thread by the same rule; both suites read one fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from pathfinder.services.strategies.naming import provisional_strategy_name

_PARITY = (
    Path(__file__).resolve().parents[8]
    / "packages"
    / "spec"
    / "provisional_name_parity.json"
)


class _Case(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    name: str
    prompt: str
    expected: str


class _Parity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    cases: list[_Case]


_CASES = _Parity.model_validate_json(_PARITY.read_text("utf-8")).cases


def test_the_fixture_holds_every_shape_the_rule_must_agree_on() -> None:
    assert [case.name for case in _CASES] == [
        "plain",
        "long-cut-on-a-word",
        "one-70-character-word",
        "emoji-at-the-cut",
        "60-code-points-in-61-code-units",
        "bom-led",
        "unicode-spaces",
        "control-characters-are-not-spaces",
        "empty",
        "spaces-only",
    ]


@pytest.mark.parametrize("case", _CASES, ids=[case.name for case in _CASES])
def test_the_name_matches_the_shared_fixture(case: _Case) -> None:
    assert provisional_strategy_name(case.prompt) == case.expected
