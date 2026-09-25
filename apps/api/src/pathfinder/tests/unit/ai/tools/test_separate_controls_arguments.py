"""The separation run refuses bad arguments at the signature, and the Lead offers
it only behind the researcher's yes."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.toolsets.wrapper import WrapperToolset
from veupathdb_mcp.separation import CandidateProposal

from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.tools.standalone.separation import SEPARATION
from pathfinder.domain.separation import (
    SEPARATION_BUDGET,
    SEPARATION_BUDGET_MAX,
    SEPARATION_BUDGET_MIN,
)

_TOOL = "separate_controls"
_POSITIVES = ["PF3D7_0100600", "PF3D7_0100800"]
_NEGATIVES = ["PF3D7_0508800"]


def _lead_tool(name: str) -> Any:
    for mounted in build_lead_agent().toolsets:
        toolset = mounted
        while isinstance(toolset, WrapperToolset):
            toolset = toolset.wrapped
        if isinstance(toolset, FunctionToolset) and name in toolset.tools:
            return toolset.tools[name]
    return pytest.fail(f"the Lead offers no tool called {name}")


def _validate(**changed: object) -> dict[str, Any]:
    arguments: dict[str, object] = {
        "positive_controls": _POSITIVES,
        "negative_controls": _NEGATIVES,
        "mode": "exact",
        "reply": "I will measure the two lists against the site's searches.",
    }
    validator = _lead_tool(_TOOL).function_schema.validator
    return dict(validator.validate_python(arguments | changed))


def test_the_arguments_the_design_names_pass() -> None:
    validated = _validate(
        literature=[
            {
                "query": "exported proteins with a PEXEL motif",
                "reference": "https://doi.org/10.1038/nature03069",
            }
        ],
        budget=SEPARATION_BUDGET_MIN,
    )

    assert validated == {
        "reply": "I will measure the two lists against the site's searches.",
        "positive_controls": _POSITIVES,
        "negative_controls": _NEGATIVES,
        "mode": "exact",
        "literature": (
            CandidateProposal(
                query="exported proteins with a PEXEL motif",
                reference="https://doi.org/10.1038/nature03069",
            ),
        ),
        "budget": SEPARATION_BUDGET_MIN,
    }


@pytest.mark.parametrize(
    "changed",
    [
        {"negative_controls": []},
        {"positive_controls": ["PF3D7_0100600"]},
        {"budget": SEPARATION_BUDGET_MIN - 1},
        {"budget": SEPARATION_BUDGET_MAX + 1},
        {"mode": "closest"},
        {"literature": [{"query": "x", "reference": "doi"}]},
    ],
)
def test_the_signature_refuses_what_the_worker_cannot_run(
    changed: dict[str, object],
) -> None:
    with pytest.raises(ValidationError) as refused:
        _validate(**changed)

    assert {str(error["loc"][0]) for error in refused.value.errors()} == set(changed)


def test_the_run_is_sequential_and_gated_on_the_users_yes() -> None:
    tool = _lead_tool(_TOOL)

    assert (tool.requires_approval, tool.sequential) == (True, True)


def test_the_budget_is_a_request_estimate_with_its_bounds() -> None:
    budget = _lead_tool(_TOOL).function_schema.json_schema["properties"]["budget"]

    assert (budget["minimum"], budget["maximum"], budget["default"]) == (200, 2000, 600)
    assert (SEPARATION_BUDGET, SEPARATION.estimated_duration_seconds) == (600, 300)
