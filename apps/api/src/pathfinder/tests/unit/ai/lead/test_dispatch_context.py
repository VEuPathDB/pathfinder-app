"""What a sub-agent dispatch carries from the thread into its tool state."""

from __future__ import annotations

from veupathdb.domain.strategy.constraints import (
    ConstraintKind,
    organism_hints_from,
)

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
    user_intent,
)

_HINT_PROMPT = "Find P. falciparum mass-spec samples."
_COMBINATION = "mass spectrometry evidence OR DeRisi expression"
_COMBINATION_PROMPT = "Kinases with mass spec evidence or DeRisi expression."
_MOTIF = "[TG].{5,6}YGCACACAN[TCA]H"
_TURN_ONE = (
    "Find A. gambiae midgut protease genes conserved across mosquito species "
    f"that are near the motif {_MOTIF} on the genome."
)
_TURN_TWO = (
    "Conserved = has an ortholog in at least two other mosquito species. "
    "Near = within 1 kb upstream of the motif. Go ahead."
)


def _threaded_state(intent: UserIntent, site_id: str = "plasmodb") -> PipelineState:
    state = pipeline_state(site_id, user_prompt=intent.raw_text)
    state.domain.record_intent(intent, request_text=intent.raw_text)
    return state


def test_only_the_organism_requirements_are_hints() -> None:
    requirements = [
        requirement(ConstraintKind.DATA_TYPE, "data type", "RNA-Seq"),
        requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum"),
        requirement(ConstraintKind.FOLD_CHANGE, "fold change", "2"),
    ]

    assert organism_hints_from(requirements) == ["Plasmodium falciparum"]


def test_the_stated_order_is_kept() -> None:
    requirements = [
        requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum"),
        requirement(ConstraintKind.OTHER, "other", "kinase"),
        requirement(ConstraintKind.ORGANISM, "organism", "Anopheles gambiae"),
    ]

    assert organism_hints_from(requirements) == [
        "Plasmodium falciparum",
        "Anopheles gambiae",
    ]


def test_a_repeated_organism_is_one_hint() -> None:
    requirements = [
        requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum"),
        requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum"),
    ]

    assert organism_hints_from(requirements) == ["Plasmodium falciparum"]


def test_no_requirement_is_no_hint() -> None:
    assert organism_hints_from([]) == []


def test_the_dispatch_deps_carry_the_organism_hints() -> None:
    intent = user_intent(
        _HINT_PROMPT,
        IntentClassification.NEW_STRATEGY,
        inferred_goal="mass-spec samples",
        explicit_constraints=[
            requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum"),
        ],
    )

    deps = agent_deps_for(lead_deps(_threaded_state(intent), intent=intent))

    assert deps.agent_state.organism_hints == ["Plasmodium falciparum"]


def test_the_dispatch_deps_carry_the_combination_requirements() -> None:
    intent = user_intent(
        _COMBINATION_PROMPT,
        IntentClassification.NEW_STRATEGY,
        inferred_goal="kinase drug targets",
        explicit_constraints=[
            requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum"),
            requirement(
                ConstraintKind.COMBINATION,
                "how the evidence combines",
                _COMBINATION,
            ),
        ],
    )

    deps = agent_deps_for(lead_deps(_threaded_state(intent), intent=intent))

    assert [c.requested_value for c in deps.agent_state.combination_requirements] == [
        _COMBINATION
    ]


def _turn_one_intent() -> UserIntent:
    return user_intent(
        _TURN_ONE,
        IntentClassification.NEW_STRATEGY,
        inferred_goal="midgut proteases near a motif",
        explicit_constraints=[
            requirement(ConstraintKind.ORGANISM, "organism", "Anopheles gambiae"),
            requirement(ConstraintKind.OTHER, "regulatory motif", _MOTIF),
        ],
    )


def _turn_two_intent() -> UserIntent:
    return user_intent(
        _TURN_TWO,
        IntentClassification.CLARIFICATION_RESPONSE,
        inferred_goal="confirm the definitions and proceed",
        explicit_constraints=[
            requirement(
                ConstraintKind.OTHER, "motif proximity", "within 1 kb upstream"
            ),
        ],
    )


def _two_turn_state() -> PipelineState:
    state = pipeline_state("vectorbase", user_prompt=_TURN_ONE)
    state.domain.record_intent(_turn_one_intent(), request_text=_TURN_ONE)
    state.user_prompt = _TURN_TWO
    state.domain.record_intent(_turn_two_intent(), request_text=_TURN_TWO)
    return state


def test_the_clarification_turn_ledger_carries_the_first_turn_values() -> None:
    ledger = derive_ledger(_two_turn_state(), _turn_two_intent())

    values = {g.constraint.requested_value for g in ledger.constraints.grounded}
    assert {"Anopheles gambiae", _MOTIF, "within 1 kb upstream"} <= values


def test_the_frame_deps_goal_carries_the_original_request_and_the_answer() -> None:
    deps = lead_deps(_two_turn_state(), intent=_turn_two_intent())

    goal = agent_deps_for(deps).agent_state.operational_spec_draft.goal

    assert _TURN_ONE in goal
    assert _TURN_TWO in goal
    assert goal.index(_TURN_ONE) < goal.index(_TURN_TWO)


def test_the_pinned_summary_lists_every_stated_requirement() -> None:
    summary = derive_ledger(_two_turn_state(), _turn_two_intent()).render_summary()

    assert "Anopheles gambiae" in summary
    assert _MOTIF in summary
    assert "within 1 kb upstream" in summary


def test_the_summary_caps_the_requirement_list() -> None:
    intent = user_intent(
        "many requirements",
        IntentClassification.NEW_STRATEGY,
        inferred_goal="many",
        explicit_constraints=[
            requirement(ConstraintKind.OTHER, f"r{i}", f"requirement {i}")
            for i in range(30)
        ],
    )
    state = pipeline_state("vectorbase", user_prompt="many requirements")
    state.domain.record_intent(intent, request_text="many requirements")

    summary = derive_ledger(state, intent).render_summary()

    assert summary.count("requirement ") == 20
    assert "10 more stated earlier" in summary
