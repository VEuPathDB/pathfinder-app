"""A sweep request that names its controls reaches the sweep with both lists."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic_ai.messages import ModelRequest, UserPromptPart

from pathfinder.ai.models.mock import arcs

_FIXTURE = (
    Path(__file__).parents[3]
    / "fixtures"
    / "controls"
    / "signal_peptide_repeated_tests.json"
)
_CALLS = json.loads(_FIXTURE.read_text())["calls"]
POSITIVES: list[str] = _CALLS[0]["positive"]
NEGATIVES: list[str] = _CALLS[0]["negative"]
REQUEST = (
    "Optimize the SignalP version of the signal peptide search to recover as many "
    "of my positive controls as possible while returning as few of my negative "
    "controls as possible. Positive controls: "
    + " ".join(POSITIVES)
    + " Negative controls: "
    + " ".join(NEGATIVES)
)


def test_the_request_leads_to_one_sweep_with_80_and_40_ids() -> None:
    sequence = arcs._lead_sequence(
        [ModelRequest(parts=[UserPromptPart(content=REQUEST)])]
    )

    sweeps = [c for c in sequence if c.tool_name == "optimize_search_parameters"]
    assert [c.tool_name for c in sequence] == [
        "classify_user_intent",
        "optimize_search_parameters",
        "final_result",
    ]
    assert len(sweeps) == 1
    args = sweeps[0].args_as_dict()
    assert (len(args["positive_controls"]), len(args["negative_controls"])) == (80, 40)
    assert args["positive_controls"] == POSITIVES
    assert args["negative_controls"] == NEGATIVES
