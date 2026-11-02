from __future__ import annotations

from pathfinder.ai.lead.intent import IntentClassification, NamedControls, UserIntent
from pathfinder.ai.lead.lead_pins import pinned_user_intent
from pathfinder.domain.message_reading import MessageReading
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.tests._support.run_context import lead_run_context


def _stated(
    kind: ConstraintKind, value: str, quote: str, *, hard: bool = True
) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        label=value,
        source=ConstraintSource.USER_EXPLICIT,
        quote=quote,
        hard=hard,
    )


def test_a_turn_with_no_intent_pins_that_it_has_none() -> None:
    assert (
        pinned_user_intent(lead_run_context()) == "## User Intent\nNot classified yet."
    )


def test_the_pin_states_what_the_message_asks_and_states() -> None:
    ctx = lead_run_context()
    ctx.deps.intent = UserIntent(
        classification=IntentClassification.EDIT_STRATEGY,
        inferred_goal="the same search at a lower cut",
        asks=["tell me the new count"],
        explicit_constraints=[
            _stated(ConstraintKind.FOLD_CHANGE, "at least 1.5-fold", "1.5 fold"),
            _stated(
                ConstraintKind.DATA_TYPE, "RNA-Seq", "RNA-Seq preferred", hard=False
            ),
        ],
        withdrawn=[
            _stated(ConstraintKind.OTHER, "signal peptide", "drop the signal peptide")
        ],
        named_controls=NamedControls(positive_ids=["PF3D7_1133400"]),
        named_gene_ids=["PF3D7_0709000"],
        reading=MessageReading(effect="change", wants="status", read_by="decisions"),
    )

    assert pinned_user_intent(ctx) == "\n".join(
        [
            "## User Intent",
            "- classification: edit_strategy",
            "- the message asks to be told: status",
            "- inferred goal: the same search at a lower cut",
            '- states fold_change: at least 1.5-fold, in its words "1.5 fold"',
            '- prefers data_type: RNA-Seq, in its words "RNA-Seq preferred"',
            '- takes back other: signal peptide, in its words "drop the signal peptide"',
            "- asks: tell me the new count",
            "- positive controls: PF3D7_1133400",
            "- names genes: PF3D7_0709000",
        ]
    )


def test_an_ask_that_is_the_whole_request_is_not_pinned_as_an_ask() -> None:
    message = "Can you also require that they are expressed in trophozoites?"
    ctx = lead_run_context(user_prompt=message)
    ctx.deps.intent = UserIntent(
        classification=IntentClassification.EXTEND_STRATEGY,
        inferred_goal="add trophozoite expression",
        asks=[message],
    )

    pinned = pinned_user_intent(ctx) or ""

    assert ("- asks:" in pinned, "- classification: extend_strategy" in pinned) == (
        False,
        True,
    )
