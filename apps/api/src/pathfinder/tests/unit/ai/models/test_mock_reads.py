"""A tool answer the arc reads either parses or fails; only a compacted answer,
which is text, reads as absent."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)

from pathfinder.ai.models.mock.reads import (
    control_set_id,
    controls_sentence,
    gene_set_id,
)


def _answered(tool: str, content: object) -> list[ModelMessage]:
    return [
        ModelResponse(parts=[ToolCallPart(tool_name=tool, args={}, tool_call_id="c1")]),
        ModelRequest(
            parts=[ToolReturnPart(tool_name=tool, content=content, tool_call_id="c1")]
        ),
    ]


def test_an_answer_that_parses_is_read() -> None:
    answered = _answered("build_control_set", {"controlSetId": "cs-9"})

    assert control_set_id(answered) == "cs-9"


def test_an_answer_of_another_shape_fails() -> None:
    answered = _answered("save_gene_set", {"geneSet": {"id": "gs-1"}})

    with pytest.raises(ValidationError, match=r"geneSetCreated"):
        gene_set_id(answered)


def test_a_compacted_answer_reads_as_absent_beside_a_parsed_one() -> None:
    answered = [
        *_answered("build_control_set", {"controlSetId": "cs-9"}),
        *_answered("build_control_set", "build_control_set returned a set."),
    ]

    assert control_set_id(answered) == "cs-9"


def test_a_repeated_control_test_is_read_for_the_outcome_it_carries() -> None:
    outcome = {
        "positiveRecoveredIds": ["a", "b"],
        "positiveMissedIds": ["c"],
        "negativeAdmittedIds": [],
        "negativeExcludedIds": ["d"],
    }
    answered = _answered(
        "run_control_tests_on_step", {"note": "Already tested.", "outcome": outcome}
    )

    assert controls_sentence(answered) == (
        "2 of 3 positive controls recovered; 0 of 1 negative controls returned."
    )
