"""The faults the turn contract and the intent gate refuse make their wrong
call once, the real rule refuses it with its own sentence, and the arc then
makes the right call."""

from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic_ai.messages import ToolCallPart

from pathfinder.ai.lead.evidence_claims import ControlList, list_claims
from pathfinder.ai.lead.intent import UserIntent, organism_refusal
from pathfinder.ai.lead.turn_contract import LeadResponse, reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.ai.models.mock.directive import without_tokens
from pathfinder.ai.models.mock.faults import made_by_a_fault
from pathfinder.ai.models.mock.reply_faults import MISSTATED_BY, UNMET_REQUIREMENT
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests._support.site_organisms import recorded_organisms
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    building_deps,
    control_test_deps,
    reading_deps,
)
from pathfinder.tests.unit.ai.models._mock_findings import (
    CONTROLS,
    UNMET,
    checked,
    holding,
)
from pathfinder.tests.unit.ai.models._mock_questions import ASKED_ORGANISM, asking_frame
from pathfinder.tests.unit.ai.models._mock_turns import (
    ADDED_SEARCH,
    SHEET_ORGANISMS,
    Scene,
    args_of,
    built_thread,
    names,
    play,
    verify_order,
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


def test_a_reply_silent_about_a_caveat_is_refused_then_states_it() -> None:
    scene = replace(
        built_thread(),
        faulted={"final_result": _REFUSED},
        answers={
            **built_thread().answers,
            "verify_strategy": checked(caveats=(CONTROLS,), gaps=()),
        },
    )
    calls = play(
        "lead",
        _SITE,
        f"Test it {_token('controls-test', 'unstated-caveat')}",
        scene=scene,
    )
    wrong, right = _finals(calls)
    record = holding(
        turn_record(run_context_for(control_test_deps())), caveats=(CONTROLS,), gaps=()
    )

    assert CONTROLS.sentence not in wrong.prose
    assert CONTROLS.sentence in right.prose
    assert [m.sentence for m in reconcile(wrong, record)] == [
        (
            f"The check measured {CONTROLS.sentence}. Your reply does not state "
            "it; give the numbers."
        )
    ]
    assert reconcile(right, record) == []
    assert len(_faulted(calls)) == 1


def test_the_setup_of_an_unstated_gap_reports_a_requirement_nothing_answers() -> None:
    calls = play(
        "verification",
        _SITE,
        _token("single", "unstated-gap"),
        work_order=verify_order(200),
    )
    rows = calls[-1].args_as_dict()["digest"]["review"]["requirements"]

    assert [(r["text"], r["status"]) for r in rows][-1] == (UNMET_REQUIREMENT, "unmet")
    assert made_by_a_fault(calls[-1]) is True


def test_a_reply_silent_about_a_gap_is_refused_then_states_it() -> None:
    scene = Scene(
        faulted={"final_result": _REFUSED},
        answers={"verify_strategy": checked(caveats=(), gaps=(UNMET,))},
    )
    calls = play("lead", _SITE, _token("single", "unstated-gap"), scene=scene)
    wrong, right = _finals(calls)
    deps = building_deps()
    deps.state.turn_markers.added_searches = [ADDED_SEARCH]
    record = holding(turn_record(run_context_for(deps)), caveats=(), gaps=(UNMET,))

    assert UNMET_REQUIREMENT not in wrong.prose
    assert UNMET.sentence in right.prose
    assert [(m.kind, m.sentence) for m in reconcile(wrong, record)] == [
        (
            "unstated_gap",
            (
                "The check found what the strategy does not answer: "
                f"{UNMET.sentence}. Your reply does not say so; state each with "
                "what is missing."
            ),
        )
    ]
    assert reconcile(right, record) == []
    assert len(_faulted(calls)) == 1


def test_a_separation_card_misstates_its_positives_once_then_the_lists() -> None:
    scene = Scene(faulted={"separate_controls": _REFUSED})
    controls = SiteValues.for_site(_SITE).controls
    positives, negatives = len(controls.positive_ids), len(controls.negative_ids)

    calls = play(
        "lead", _SITE, _token("separation", "misstated-control-list"), scene=scene
    )
    replies = [str(a["reply"]) for a in args_of(calls, "separate_controls")]

    assert [
        [(claim.stated, claim.kind) for claim in list_claims(reply)]
        for reply in replies
    ] == [
        [(positives - MISSTATED_BY, "positive"), (negatives, "negative")],
        [(positives, "positive"), (negatives, "negative")],
    ]
    held = (ControlList("positive", positives), ControlList("negative", negatives))
    record = turn_record(run_context_for(reading_deps())).model_copy(
        update={"control_lists": held, "ends_on_a_card": True}
    )
    wrong, right = (
        LeadResponse(prose=reply, strategy_changed=False) for reply in replies
    )
    assert [(m.kind, m.sentence) for m in reconcile(wrong, record)] == [
        (
            "misstated_control_list",
            (
                f"Your reply says {positives - MISSTATED_BY} positive controls; the "
                f"lists this turn holds are {positives} positive and {negatives} "
                "negative controls. Return the same reply with each list stated at "
                "the size the turn holds."
            ),
        )
    ]
    assert reconcile(right, record) == []
    assert len(_faulted(calls)) == 1


@pytest.mark.parametrize("site_id", SITES)
def test_a_split_organism_is_refused_by_the_gate_then_recorded_whole(
    site_id: str,
) -> None:
    organism = SiteValues.for_site(site_id).organism
    binomial, strain = organism.rsplit(" ", 1)
    text = f"Find {organism} genes whose proteins have a predicted signal peptide."
    scene = Scene(faulted={"classify_user_intent": _REFUSED})

    calls = play(
        "lead", site_id, f"{text} {_token('single', 'organism-split')}", scene=scene
    )
    wrong, right = [
        UserIntent.model_validate(a["intent"])
        for a in args_of(calls, "classify_user_intent")
    ]

    assert [(c.kind.value, c.requested_value) for c in wrong.explicit_constraints] == [
        ("organism", binomial),
        ("other", f"{strain} genes"),
    ]
    assert right.explicit_constraints == []
    assert organism_refusal(
        wrong, without_tokens(text), recorded_organisms(site_id)
    ) == (
        f'The message names the organism "{organism}", one entry of this '
        "site's organism list. Record it whole as the organism constraint; "
        f'"{strain}" is part of its name, not a requirement of its own.'
    )
    assert len(_faulted(calls)) == 1


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
    assert wrong.prose == f"{ASKED_ORGANISM} I recommend {SHEET_ORGANISMS[_SITE][0]}."
    assert [(m.kind, m.sentence) for m in reconcile(wrong, record)] == [
        (
            "open_value_in_prose",
            (
                f'The spec leaves "{ASKED_ORGANISM}" open. Ask it on the question '
                "card (consult_user) with its options; a question in prose is "
                "refused."
            ),
        )
    ]
    assert len(_faulted(calls)) == 1
