"""The consult arc: FRAME leaves the organism open and asks it with the options
the sheet offers, the Lead asks it on the question card, and the answer is
framed, built and checked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from assistant_core.models.scripted import (
    current_scope_id,
    deferred_tool_resolved,
    scripted_call,
)
from pydantic import Field
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolCallPart,
    ToolReturnPart,
)

from pathfinder.ai.models.mock.calls import classify, lead_final
from pathfinder.ai.models.mock.history import acted_tool_names, head_work_order
from pathfinder.ai.models.mock.lead_flow import build_journey, run_sequence
from pathfinder.ai.models.mock.reads import (
    ToolAnswer,
    frame_summary,
    instructions_of,
    last_return,
    pinned_on,
)
from pathfinder.ai.models.mock.sheets import sheet_entries
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.specs import (
    CriterionSpec,
    SpecPlan,
    criterion_call,
    criterion_replies,
    leaf,
    proposal_args,
    set_structure_args,
    sheet_call_args,
)
from pathfinder.ai.models.mock.strategy_specs import signal_peptide

CONSULT = "consult_user"
OPEN_PARAM = "organism"
OPEN_QUESTION = "Which organism should the signal peptide search read?"
CARD_REPLY = (
    "[mock] One value decides the steps, so I ask it before I build: the "
    "organism the search reads."
)
# The card offers at most this many options, as the frame result holds them.
_OPTIONS = 8
_ANSWER = re.compile(r"^Answer: .*?-> (?P<chosen>[^;\n]+)", re.MULTILINE)


def _site() -> SiteValues:
    return SiteValues.for_site(current_scope_id.get())


def _criterion(organism: str | None) -> CriterionSpec:
    """The signal peptide criterion, its organism open or set to ``organism``."""
    crit = signal_peptide(_site())
    held = {name: v for name, v in crit.values.items() if name != OPEN_PARAM}
    values = held if organism is None else {**held, OPEN_PARAM: [organism]}
    return replace(
        crit,
        text="genes with a predicted signal peptide",
        values=values,
        site_organism="",
    )


def _spec(crit: CriterionSpec) -> SpecPlan:
    return SpecPlan(title=crit.text, criteria=(crit,), structure=leaf(crit))


@dataclass(frozen=True)
class _Offer:
    """The options a question offers, and the one it recommends."""

    options: list[str]
    recommended: str


def _offer(vocabulary: list[str], *, opened: bool) -> _Offer | None:
    """The values the sheet lists for the open organism, the site organism and
    its genus first, at most eight, the site organism recommended. None when
    the tool opened no slot."""
    if not opened or not vocabulary:
        return None
    organism = _site().organism
    genus = organism.split()[0]
    kin = [v for v in vocabulary if v.split()[0] == genus and v != organism]
    rest = [v for v in vocabulary if v not in kin and v != organism]
    first = [organism] if organism in vocabulary else []
    options = [*first, *kin, *rest][:_OPTIONS]
    return _Offer(options=options, recommended=options[0])


def _sheet_vocabulary(messages: list[ModelMessage], crit: CriterionSpec) -> list[str]:
    """Every value the sheet lists for the organism, from the newest request
    that pinned it: binding the criterion closes the sheet."""
    pinned = (
        sheet_entries(pinned_on(message) or "", crit.criterion_id)
        for message in reversed(messages)
    )
    entries = next((found for found in pinned if found), [])
    return [
        option.value
        for entry in entries
        if entry.name == OPEN_PARAM
        for option in entry.vocabulary or []
    ]


def _slot_options(
    messages: list[ModelMessage], crit: CriterionSpec
) -> list[str] | None:
    """The options the binding's open organism slot offers, empty when the tool
    opened none, or None before the binding answered."""
    bound = [
        r
        for r in criterion_replies(messages)
        if r.criterion_id == crit.criterion_id and r.resolved_params
    ]
    if not bound:
        return None
    return [
        o for s in bound[-1].open_slots if s.param_name == OPEN_PARAM for o in s.options
    ]


def _asked(crit: CriterionSpec, offer: _Offer | None) -> dict[str, Any]:
    if offer is None:
        return {
            "summary": f"Framed 1 criterion(s) for {crit.text}.",
            "disposition": "spec_ready",
            "openQuestions": [],
        }
    return {
        "summary": f"The signal peptide search needs its organism: {crit.text}.",
        "disposition": "needs_user",
        "openQuestions": [
            {
                "question": OPEN_QUESTION,
                "dimension": "organism",
                "recommendedValue": offer.recommended,
                "options": offer.options,
            }
        ],
    }


def _catalog_read(called: frozenset[str], crit: CriterionSpec) -> ToolCallPart | None:
    """The catalog reads a pass makes before it binds, each once."""
    if "search_for_searches" not in called:
        return scripted_call("search_for_searches", {"query": crit.text})
    if "list_searches" not in called:
        return scripted_call("list_searches", {"record_type": "transcript"})
    return None


def _asking_frame(messages: list[ModelMessage]) -> ToolCallPart:
    """Bind the criterion with the organism open, then ask it."""
    called = acted_tool_names(messages)
    crit = _criterion(None)
    read = _catalog_read(called, crit)
    if read is not None:
        return read
    slot_options = _slot_options(messages, crit)
    if slot_options is None:
        call = criterion_call(
            crit, criterion_replies(messages), instructions_of(messages)
        )
        if call is not None:
            return call
    if "set_structure" not in called:
        return scripted_call("set_structure", set_structure_args(_spec(crit)))
    offer = _offer(_sheet_vocabulary(messages, crit), opened=bool(slot_options))
    return scripted_call("final_result", _asked(crit, offer))


def _answered_frame(messages: list[ModelMessage], organism: str) -> ToolCallPart:
    """Bind the criterion again on the organism the researcher chose."""
    called = acted_tool_names(messages)
    crit = _criterion(organism)
    read = _catalog_read(called, crit)
    if read is not None:
        return read
    own = [
        r for r in criterion_replies(messages) if r.criterion_id == crit.criterion_id
    ]
    sheets = [r.params_template for r in own if r.params_template]
    if not any(r.resolved_params for r in own):
        if not sheets:
            return scripted_call("set_criterion", sheet_call_args(crit))
        args = proposal_args(crit, sheets[-1], instructions_of(messages))
        return scripted_call("set_criterion", args)
    if "set_structure" not in called:
        return scripted_call("set_structure", set_structure_args(_spec(crit)))
    return scripted_call(
        "final_result",
        {
            "summary": f"Bound the organism the researcher chose: {organism}.",
            "disposition": "spec_ready",
            "openQuestions": [],
            "changes": [{"criterionId": crit.criterion_id, "disposition": "changed"}],
        },
    )


def open_value_frame(messages: list[ModelMessage]) -> ToolCallPart:
    """Ask the organism on a fresh order, and bind it on an order that carries
    the answer."""
    answer = _ANSWER.search(head_work_order(messages))
    if answer is None:
        return _asking_frame(messages)
    return _answered_frame(messages, answer["chosen"].strip())


class _Question(ToolAnswer):
    question: str
    recommended_value: str = ""
    options: list[str] = Field(default_factory=list)


class _Framed(ToolAnswer):
    disposition: str = ""
    open_questions: list[_Question] = Field(default_factory=list)


def open_questions(messages: list[ModelMessage]) -> list[_Question]:
    """The questions the newest frame pass left for the researcher."""
    framed = last_return(messages, "frame_problem", _Framed)
    if framed is None or framed.disposition != "needs_user":
        return []
    return framed.open_questions


def card_args(questions: list[_Question]) -> dict[str, Any]:
    """One card question per open question, its options from the frame, the
    recommended one marked."""
    return {
        "reply": CARD_REPLY,
        "questions": [
            {
                "id": f"q{index}",
                "prompt": q.question,
                "kind": "single_choice",
                "options": [
                    {"label": o, "recommended": o == q.recommended_value}
                    for o in q.options
                ],
            }
            for index, q in enumerate(questions, 1)
        ],
    }


def _answers_the_card(message: ModelMessage) -> bool:
    match message:
        case ModelRequest(parts=parts):
            return any(_returns_the_card(part) for part in parts)
        case _:
            return False


def _returns_the_card(part: object) -> bool:
    match part:
        case ToolReturnPart(tool_name=name):
            return name == CONSULT
        case _:
            return False


def _since_the_answer(messages: list[ModelMessage]) -> list[ModelMessage]:
    """The run after the card's answer came back."""
    answered = [i for i, message in enumerate(messages) if _answers_the_card(message)]
    return messages[answered[-1] :] if answered else messages


def _asking(messages: list[ModelMessage]) -> list[ToolCallPart]:
    head = [
        classify("new_strategy"),
        scripted_call("frame_problem", {"reason": "mock frame"}),
    ]
    asked = open_questions(messages)
    if asked:
        return [*head, scripted_call(CONSULT, card_args(asked))]
    return [
        *head,
        lead_final(f"{frame_summary(messages)} I built nothing.", "await_user"),
    ]


def consult(messages: list[ModelMessage]) -> ToolCallPart:
    """Frame and ask the open value on the card; the answered card resumes on
    a frame of the answer, the build and its check."""
    if not deferred_tool_resolved(messages, CONSULT):
        return run_sequence(messages, _asking(messages))
    return run_sequence(_since_the_answer(messages), build_journey(messages))
