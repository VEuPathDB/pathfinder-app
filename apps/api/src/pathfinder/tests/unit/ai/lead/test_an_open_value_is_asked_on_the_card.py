"""A value the frame leaves open is asked on the question card, never in prose."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import DeferredToolRequests
from veupathdb.wdk import WDKSearchResponse
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.card_contract import hold_the_contract_on_a_card
from pathfinder.ai.lead.ledger_render import render_frame_full
from pathfinder.ai.lead.ledger_sections import FrameSection
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse, reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import (
    OpenQuestion,
    SlotQuestion,
)
from pathfinder.tests._support.qa_recording import client_recording
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

# The question FRAME asked on N1, with the facets it read on the sheet.
_CUTOFF = SlotQuestion(
    question="Which cutoff should define low variation between isolates?",
    dimension=ConstraintKind.STATISTICAL_THRESHOLD,
    recommended_value="maximum minor-allele frequency <= 1%",
    criterion_id="c_var",
    param_name="max_minor_allele_frequency",
    options=[
        "maximum minor-allele frequency <= 1%",
        "maximum minor-allele frequency <= 5%",
        "maximum variants per kb",
    ],
).typed()
_N1_PROSE = (
    "I can build this strategy, but one value is open. Which cutoff should I "
    "use? I recommend the strictest minor-allele frequency the card offers."
)
_OPEN_SENTENCE = (
    'The spec leaves "Which cutoff should define low variation between '
    'isolates?" open. Ask it on the question card (consult_user) with its '
    "options; a question in prose is refused."
)
_CUTOFF_SLOT = OpenSlot(
    criterion_id="c_var",
    param_name="max_minor_allele_frequency",
    question=_CUTOFF.question,
)
_GROUP_SLOT = OpenSlot(
    criterion_id="c_eda",
    param_name="comparator",
    question="Which group is the comparator?",
    options=["sporozoite", "liver stage", "blood stage"],
)


def _framed(*, asked: list[OpenQuestion], at_arrival: list[str]) -> LeadDeps:
    """A turn whose FRAME pass ran, holding the questions a test names."""
    state = pipeline_state(
        user_prompt="Genes that vary little.", user_message_id=uuid4()
    )
    state.turn_markers.framed = True
    state.turn_markers.questions_at_arrival = at_arrival
    state.domain.open_questions = asked
    state.domain.operational_spec = _spec(open_params=[_CUTOFF_SLOT])
    return lead_deps(state)


def _spec(*, open_params: list[OpenSlot]) -> OperationalSpec:
    """N1's variation criterion, bound or holding the slots a test names."""
    return OperationalSpec(
        goal="genes that vary little between isolates",
        criteria=[
            Criterion(
                id="c_var",
                text="low variation between isolates",
                search_name="GenesByVariantCharacteristics",
                open_params=open_params,
            )
        ],
    )


def test_a_question_asked_by_pass_one_and_closed_by_pass_two_stands() -> None:
    deps = _framed(asked=[_CUTOFF], at_arrival=[])
    assert _kinds(deps, _N1_PROSE) == ["open_value_in_prose"]

    deps.state.domain.operational_spec = _spec(open_params=[])

    assert _kinds(deps, "I built it with the strictest minor-allele frequency.") == []


def test_a_spec_ready_pass_with_a_question_asks_nothing_of_the_card() -> None:
    deps = _framed(asked=[_CUTOFF], at_arrival=[])
    deps.state.domain.operational_spec = _spec(open_params=[])

    assert _kinds(deps, _N1_PROSE) == []


def _kinds(deps: LeadDeps, prose: str) -> list[str]:
    report = LeadResponse(prose=prose, strategy_changed=False)
    return [m.kind for m in reconcile(report, turn_record(run_context_for(deps)))]


def test_n1_s_open_cutoff_asked_in_prose_is_refused() -> None:
    deps = _framed(asked=[_CUTOFF], at_arrival=[])
    report = LeadResponse(prose=_N1_PROSE, strategy_changed=False)

    found = reconcile(report, turn_record(run_context_for(deps)))

    assert [(m.kind, m.sentence) for m in found] == [
        ("open_value_in_prose", _OPEN_SENTENCE)
    ]


def test_the_same_turn_ending_on_the_question_card_is_shown() -> None:
    deps = _framed(asked=[_CUTOFF], at_arrival=[])
    card = ToolCallPart(
        tool_name="consult_user",
        args={
            "reply": "One value is open before I build: the variation cutoff.",
            "questions": [{"id": "q1", "prompt": _CUTOFF.question}],
        },
        tool_call_id="call_consult",
    )

    held = hold_the_contract_on_a_card(
        run_context_for(deps), DeferredToolRequests(approvals=[card])
    )

    assert (held.approvals if held is not None else {}) == {}


def test_an_open_slot_with_a_vocabulary_asked_in_prose_is_refused() -> None:
    deps = _framed(asked=[], at_arrival=[])
    deps.state.domain.operational_spec = OperationalSpec(
        goal="genes up in one stage",
        criteria=[
            Criterion(id="c_eda", text="up in liver stage", open_params=[_GROUP_SLOT])
        ],
    )

    assert _kinds(deps, "Which group should be the comparator?") == [
        "open_value_in_prose"
    ]


def test_a_question_open_before_the_message_on_a_turn_that_did_not_frame_stands() -> (
    None
):
    deps = _framed(asked=[_CUTOFF], at_arrival=[_CUTOFF.question])
    deps.state.turn_markers.framed = False

    assert _kinds(deps, "The cutoff is still yours to choose.") == []


def test_a_framed_turn_with_nothing_open_asks_nothing_of_the_card() -> None:
    deps = _framed(asked=[], at_arrival=[])
    deps.state.domain.operational_spec = _spec(open_params=[])

    assert _kinds(deps, "Is the asexual study right? The spec is ready to build.") == []


def test_an_open_question_holds_at_most_eight_options() -> None:
    assert OpenQuestion(question="Which?").options == []
    with pytest.raises(ValidationError):
        SlotQuestion(question="Which?", options=[str(n) for n in range(9)])


def test_the_ledger_prints_each_open_slot_s_choices() -> None:
    spec = OperationalSpec(
        goal="g",
        criteria=[
            Criterion(id="c_eda", text="up in liver stage", open_params=[_GROUP_SLOT])
        ],
    )

    rendered = render_frame_full(FrameSection(spec=spec)).splitlines()

    assert (
        "    OPEN comparator: Which group is the comparator?; "
        "options: sporozoite | liver stage | blood stage"
    ) in rendered


def test_the_ledger_counts_a_vocabulary_no_card_can_hold() -> None:
    slot = _GROUP_SLOT.model_copy(update={"options": [f"g{n}" for n in range(11)]})
    spec = OperationalSpec(goal="g", open_slots=[slot])

    rendered = render_frame_full(FrameSection(spec=spec)).splitlines()

    assert "- c_eda.comparator: Which group is the comparator?; 11 values" in rendered


def test_the_ledger_prints_the_values_frame_s_card_offers_for_a_slot() -> None:
    """The VectorBase organism slot lists ticks first; the card offers mosquitoes."""
    organisms = [
        option.value
        for info in format_param_info_typed(
            WDKSearchResponse.model_validate(
                client_recording("search_genes_by_gene_model_chars").json_body()
            ).search_data.parameters
            or []
        )
        if info.name == "organism_select_none"
        for option in info.vocabulary()
    ]
    slot = OpenSlot(
        criterion_id="c_mosq",
        param_name="organism",
        question="Which organism?",
        options=organisms,
    )
    criterion = Criterion(id="c_mosq", text="mosquito genes", open_params=[slot])
    card = SlotQuestion(
        question="Which mosquito?",
        criterion_id="c_mosq",
        param_name="organism",
        options=["Anopheles gambiae PEST", "Aedes aegypti LVP_AGWG"],
    ).typed(criterion, noun="gene")
    spec = OperationalSpec(goal="g", criteria=[criterion])

    rendered = render_frame_full(
        FrameSection(spec=spec, open_questions=[card])
    ).splitlines()

    assert (
        "    OPEN organism: Which organism?; "
        "card: Anopheles gambiae PEST | Aedes aegypti LVP_AGWG"
    ) in rendered


def test_the_lead_asks_an_open_value_on_the_card() -> None:
    instructions = " ".join(LEAD_INSTRUCTIONS.split())

    assert (
        '``disposition = "needs_user"`` -> the spec has an open param slot (a value '
        "only the user can choose) or a dropped criterion. Call ``consult_user`` with "
        "the result's ``cardQuestions`` as its questions, verbatim: each option binds "
        "the value it names; a value the options do not hold is the answer's note."
    ) in instructions
    assert "single parameter value" not in instructions
    assert "ask it in prose" not in instructions
    assert 'NEVER use it to confirm "should I build?" or "proceed?".' in instructions
