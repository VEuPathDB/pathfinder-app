from __future__ import annotations

import pytest
from veupathdb.domain.parameters import PHYLETIC_EXPRESSION_PARAM

from pathfinder.domain.strategy.expression_handles import same_wire_value

_WRITTEN = "pfal=0 AND tgon>=1 OR pfal=1 AND tgon>=2"
_GROUPED = "(pfal=0 AND tgon>=1) OR (pfal=1 AND tgon>=2)"


def test_redundant_parentheses_are_one_expression() -> None:
    assert same_wire_value(PHYLETIC_EXPRESSION_PARAM, _WRITTEN, _GROUPED)


def test_parentheses_that_regroup_terms_are_another_expression() -> None:
    assert not same_wire_value(
        PHYLETIC_EXPRESSION_PARAM,
        "pfal=0 AND tgon>=1 OR pfal>=1",
        "pfal=0 AND (tgon>=1 OR pfal>=1)",
    )


def test_another_name_is_compared_as_written() -> None:
    assert not same_wire_value("text_expression", _WRITTEN, _GROUPED)


@pytest.mark.parametrize(
    "name", [PHYLETIC_EXPRESSION_PARAM, "text_expression"], ids=["expression", "text"]
)
def test_one_writing_that_does_not_parse_equals_itself(name: str) -> None:
    assert same_wire_value(name, "pfal=0 AND", "pfal=0 AND")


def test_a_writing_that_does_not_parse_differs_from_another() -> None:
    assert not same_wire_value(PHYLETIC_EXPRESSION_PARAM, "pfal=0 AND", "pfal=0 OR")
