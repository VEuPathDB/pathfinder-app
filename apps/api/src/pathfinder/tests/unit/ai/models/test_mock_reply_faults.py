"""The faults the turn contract refuses make their wrong call once, the real
rule refuses it, and the arc then makes the right call. A misreading fault
leaves the arc's calls as they are."""

from __future__ import annotations

import pytest
from pydantic_ai.messages import ToolCallPart

from pathfinder.ai.lead.turn_contract import (
    LeadResponse,
    reconcile,
)
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.ai.models.mock.faults import made_by_a_fault
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    reading_deps,
)
from pathfinder.tests.unit.ai.models._mock_questions import (
    ASKED_ORGANISM,
    ORGANISM_LABEL,
    asking_frame,
)
from pathfinder.tests.unit.ai.models._mock_turns import (
    SHEET_ORGANISMS,
    Scene,
    names,
    play,
)

_REFUSED = "refused by the guard"
_SITE = "plasmodb"
SITES = ("plasmodb", "vectorbase")


def _token(arc: str, fault: str) -> str:
    return f"[[arc:{arc}]][[fault:{fault}]]"


def _faulted(calls: list[ToolCallPart]) -> list[ToolCallPart]:
    return [call for call in calls if made_by_a_fault(call)]


def _finals(calls: list[ToolCallPart]) -> list[LeadResponse]:
    return [
        LeadResponse.model_validate(call.args_as_dict())
        for call in calls
        if call.tool_name == "final_result"
    ]


@pytest.mark.parametrize("site_id", SITES)
def test_a_split_organism_leaves_the_arcs_calls_as_they_are(site_id: str) -> None:
    calls = play("lead", site_id, f"Find genes {_token('single', 'organism-split')}")

    assert names(calls)[:2] == ["frame_problem", "build_strategy"]
    assert _faulted(calls) == []


def test_an_open_value_asked_in_prose_is_refused_then_asked_on_the_card() -> None:
    scene = Scene(
        faulted={"final_result": _REFUSED},
        answers={"frame_problem": asking_frame(_SITE)},
    )

    calls = play("lead", _SITE, _token("consult", "open-value-in-prose"), scene=scene)
    wrong = _finals(calls)[0]
    record = turn_record(run_context_for(reading_deps())).model_copy(
        update={"frame_open_questions": (ASKED_ORGANISM,)}
    )

    assert names(calls)[:3] == [
        "frame_problem",
        "final_result",
        "consult_user",
    ]
    assert wrong.prose == (
        f"{ASKED_ORGANISM} I recommend {ORGANISM_LABEL} {SHEET_ORGANISMS[_SITE][0]}."
    )
    first = reconcile(wrong, record)[0]
    assert (first.kind, first.sentence) == (
        "open_value_in_prose",
        (
            f'The spec leaves "{ASKED_ORGANISM}" open. Ask it on the question '
            "card (consult_user) with its options; a question in prose is "
            "refused."
        ),
    )
    assert len(_faulted(calls)) == 1
