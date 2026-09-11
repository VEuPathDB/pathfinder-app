"""The typed unwrap the suite reads a tool return value through."""

from __future__ import annotations

import pytest
from pydantic import BaseModel
from pydantic_ai.messages import ToolReturn

from pathfinder.tests._support.tool_returns import returned, summary_text


class Outcome(BaseModel):
    criteria_combined: int


class OtherOutcome(BaseModel):
    label: str


def test_a_model_value_reads_back_as_that_model() -> None:
    """A tool that returns a model hands the same instance to the test."""
    outcome = Outcome(criteria_combined=2)
    result: ToolReturn[Outcome] = ToolReturn(return_value=outcome)

    assert returned(result, Outcome) is outcome


def test_a_list_value_reads_back_as_the_listed_shape() -> None:
    """A tool that returns rows hands the rows to the test."""
    result: ToolReturn[list[str]] = ToolReturn(return_value=["GenesByTaxon"])

    assert returned(result, list[str]) == ["GenesByTaxon"]


def test_a_mapping_value_reads_back_as_the_mapped_shape() -> None:
    """A tool that returns one row hands the row to the test."""
    result: ToolReturn[dict[str, str]] = ToolReturn(return_value={"name": "Genes"})

    assert returned(result, dict[str, str])["name"] == "Genes"


def test_another_shape_names_the_type_the_tool_returned() -> None:
    """A value of the wrong shape fails the test and names what came back."""
    result: ToolReturn[OtherOutcome] = ToolReturn(return_value=OtherOutcome(label="no"))

    with pytest.raises(AssertionError, match="OtherOutcome"):
        returned(result, Outcome)


def test_a_text_content_reads_back_as_the_summary_line() -> None:
    """A tool that writes a summary line hands that line to the test."""
    result: ToolReturn[Outcome] = ToolReturn(
        return_value=Outcome(criteria_combined=2), content="Winner: b"
    )

    assert summary_text(result) == "Winner: b"


def test_content_that_is_not_text_names_what_the_tool_wrote() -> None:
    """A tool return with no summary line fails the test and says so."""
    result: ToolReturn[Outcome] = ToolReturn(return_value=Outcome(criteria_combined=2))

    with pytest.raises(AssertionError, match="NoneType"):
        summary_text(result)
