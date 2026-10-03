"""The faults the turn contract refuses make their wrong call once, the real
rule refuses it, and the arc then makes the right call. A split organism is
recorded whole by the intent gate and the arc goes on."""

from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic_ai.messages import ToolCallPart

from pathfinder.ai.lead import classification_gate
from pathfinder.ai.lead.intent import ClassifiedIntent, UserIntent
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.ai.lead.turn_contract import LeadResponse, reconcile, unrendered_prose
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.ai.models.mock.directive import without_tokens
from pathfinder.ai.models.mock.faults import made_by_a_fault
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests._support.site_organisms import recorded_organisms
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    building_deps,
    reading_deps,
)
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.ai.models._mock_questions import (
    ASKED_ORGANISM,
    ORGANISM_LABEL,
    asking_frame,
)
from pathfinder.tests.unit.ai.models._mock_turns import (
    SHEET_ORGANISMS,
    Scene,
    args_of,
    built_thread,
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


def test_a_written_count_is_refused_then_the_reply_writes_none() -> None:
    scene = replace(built_thread(), faulted={"final_result": _REFUSED})
    calls = play("lead", _SITE, _token("single", "unshown-count"), scene=scene)
    wrong, right = _finals(calls)
    record = turn_record(run_context_for(building_deps()))
    refused = unrendered_prose([wrong.prose], record)

    assert (None if refused is None else refused.kind) == "unrendered_prose"
    assert (unrendered_prose([right.prose], record), reconcile(right, record)) == (
        None,
        [],
    )
    assert len(_faulted(calls)) == 1


@pytest.mark.parametrize("site_id", SITES)
async def test_a_split_organism_is_recorded_whole_by_the_gate(
    site_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    organism = SiteValues.for_site(site_id).organism
    binomial, strain = organism.rsplit(" ", 1)
    text = f"Find {organism} genes whose proteins have a predicted signal peptide."

    async def _organisms(site: str) -> list[str]:
        return recorded_organisms(site)

    monkeypatch.setattr(classification_gate, "list_organisms", _organisms)
    calls = play("lead", site_id, f"{text} {_token('single', 'organism-split')}")
    [split] = [
        UserIntent.model_validate(a["intent"])
        for a in args_of(calls, "classify_user_intent")
    ]
    state = pipeline_state(site_id, user_prompt=without_tokens(text))
    returned = await classify_user_intent(
        run_context_for(lead_deps(state), tool_call_id="call_classify"), split
    )

    assert [(c.kind.value, c.requested_value) for c in split.explicit_constraints] == [
        ("organism", binomial),
        ("other", f"{strain} genes"),
    ]
    assert ClassifiedIntent.model_validate(returned.return_value).corrections == [
        f'organism recorded as "{organism}"'
    ]
    assert names(calls)[:2] == ["classify_user_intent", "frame_problem"]
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

    assert names(calls)[:4] == [
        "classify_user_intent",
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
