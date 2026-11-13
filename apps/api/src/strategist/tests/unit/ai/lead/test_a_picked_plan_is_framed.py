from __future__ import annotations

from uuid import uuid4

from veupathdb.domain.parameters import StringValue

from strategist.ai.graph.state import PipelineState
from strategist.ai.lead.dispatch_context import framing_goal
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.reading_plan import OfferedReading

_LABEL = "Transmembrane Domain Count: 7, 7"
_PLAN = OperationalSpec(
    goal=_LABEL,
    criteria=[
        Criterion(
            id="tm",
            text="tm",
            search_name="GenesByTransmembraneDomains",
            search_display_name="Transmembrane Domain Count",
            resolved_params={
                "min_tm": BoundValue(value=StringValue(value="7"), source="card"),
                "max_tm": BoundValue(value=StringValue(value="7"), source="card"),
            },
        )
    ],
    structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id="tm")),
)
_PLAN_LINES = (
    "The researcher picked this plan, which Explore proposed. Frame it as stated, "
    "and change it only where a requirement or the site disagrees:\n"
    "- tm: GenesByTransmembraneDomains (Transmembrane Domain Count), min_tm=7, max_tm=7\n"
    "- structure: tm"
)


def _state(prompt: str, *, also: str = "") -> PipelineState:
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="veupathdb",
        mode="build",
        user_prompt=prompt,
    )
    state.domain.offer_reading(
        OfferedReading(label=_LABEL, plan=_LABEL, gene_count=219, spec=_PLAN, also=also)
    )
    return state


def test_the_build_message_of_an_offered_plan_frames_that_plan() -> None:
    prompt = f'Build "{_LABEL}".'

    assert framing_goal(_state(prompt)) == f"{prompt}\n\n{_PLAN_LINES}"


def test_words_explore_added_are_framed_with_the_plan() -> None:
    prompt = f'Build "{_LABEL}".'
    also = "Then map the result to orthologs in Aedes aegypti."

    assert framing_goal(_state(prompt, also=also)) == (
        f"{prompt}\n\n{_PLAN_LINES}\nExplore also suggested: {also}"
    )


def test_a_message_naming_no_offered_plan_frames_its_words() -> None:
    assert framing_goal(_state('Build "another plan".')) == 'Build "another plan".'


def test_a_plan_picked_on_the_card_is_framed() -> None:
    state = _state("")
    state.domain.original_request = "Find 7-TM proteins."
    state.domain.pick_reading(_LABEL)

    assert framing_goal(state) == f"Find 7-TM proteins.\n\n{_PLAN_LINES}"


def test_a_new_request_keeps_what_explore_proposed() -> None:
    state = _state(f'Build "{_LABEL}".')

    state.domain.take_a_new_request(strategy_has_steps=False)

    assert list(state.domain.offered_readings) == [_LABEL]
