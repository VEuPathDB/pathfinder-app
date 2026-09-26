"""A test message names its arc with one token; a message with none is echoed."""

from __future__ import annotations

import contextvars

import pytest
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from pathfinder.ai.models.mock import turn_directive
from pathfinder.ai.models.mock.directive import (
    ArcDirective,
    MalformedTokenError,
    directive_of,
)
from pathfinder.ai.models.mock.faults import UnknownFaultError
from pathfinder.ai.models.mock.registry import ARCS, UnknownArcError, arc_named
from pathfinder.tests.unit.ai.models._mock_turns import names, play


def test_a_token_names_the_arc() -> None:
    assert directive_of("Find kinases [[arc:intersect]]") == ArcDirective(
        arc="intersect"
    )


def test_a_fault_token_follows_the_arc_token() -> None:
    directive = directive_of("[[arc:intersect]][[fault:rationale]] Find kinases")

    assert directive == ArcDirective(arc="intersect", fault="rationale")


def test_a_message_with_no_token_is_the_echo() -> None:
    assert directive_of("Find 3D7 genes that do not vary much") == ArcDirective()


def test_the_clear_command_the_product_writes_names_the_clear_arc() -> None:
    text = "Clear the current strategy by calling clear_strategy with confirm=true."

    assert directive_of(text) == ArcDirective(arc="clear")


def test_a_sentence_with_no_token_is_echoed_word_for_word() -> None:
    calls = play("lead", "plasmodb", "Find 3D7 trophozoite genes that vary much")

    assert names(calls) == ["final_result"]
    assert calls[0].args_as_dict()["prose"] == (
        "[mock] Find 3D7 trophozoite genes that vary much"
    )


@pytest.mark.parametrize(
    "text",
    [
        "Find kinases [[arc:Intersect]]",
        "Find kinases [[arc:single_x]]",
        "Find kinases [[ arc:single ]]",
        "Find kinases [[arc: single]]",
        "Find kinases [[ARC:single]]",
        "Find kinases [[arc:]]",
        "Find kinases [[fault:Long-Reason]] [[arc:single]]",
    ],
)
def test_a_malformed_token_fails_instead_of_echoing(text: str) -> None:
    with pytest.raises(MalformedTokenError):
        directive_of(text)


def test_a_fault_with_no_arc_fails() -> None:
    with pytest.raises(MalformedTokenError, match="long-reason"):
        directive_of("[[fault:long-reason]] hi")


def test_a_second_arc_token_fails() -> None:
    with pytest.raises(MalformedTokenError, match="intersect"):
        directive_of("[[arc:single]] then [[arc:intersect]]")


def test_a_second_fault_token_fails() -> None:
    with pytest.raises(MalformedTokenError, match="rationale"):
        directive_of("[[arc:single]][[fault:long-reason]][[fault:rationale]]")


def test_a_fault_token_apart_from_the_arc_token_still_counts() -> None:
    directive = directive_of("[[arc:single]] Find kinases [[fault:long-reason]]")

    assert directive == ArcDirective(arc="single", fault="long-reason")


def test_the_injection_token_is_no_arc_token() -> None:
    assert directive_of("[[pathfinder-injection-test]]") == ArcDirective()


def test_an_arc_the_registry_does_not_hold_fails_loudly() -> None:
    with pytest.raises(UnknownArcError, match="intersekt"):
        arc_named("intersekt")


def test_a_misspelt_token_fails_the_turn_instead_of_echoing() -> None:
    with pytest.raises(UnknownArcError, match="intersekt"):
        play("lead", "plasmodb", "Find kinases [[arc:intersekt]]")


def test_a_fault_the_registry_does_not_hold_fails_loudly() -> None:
    with pytest.raises(UnknownFaultError, match="nosuch"):
        play("frame", "plasmodb", "[[arc:single]][[fault:nosuch]]")


def test_the_registry_holds_every_named_arc() -> None:
    assert sorted(ARCS) == sorted(
        [
            "single",
            "intersect",
            "union",
            "minus",
            "orthologs",
            "syntenic-orthologs",
            "round-trip",
            "go",
            "combined",
            "edit-param",
            "add-step",
            "delete-step",
            "delete-step-card",
            "replace-subtree",
            "clear",
            "count-question",
            "gene-question",
            "consult",
            "no-search-states-it",
            "cross-organism",
            "zero-then-relax",
            "proposal",
            "portal-only",
            "other-site-experiment",
            "off-topic",
            "remember",
            "recall-preference",
            "context",
            "second-build",
            "controls-test",
            "sweep",
            "separation",
            "variants",
            "eda-compare",
            "eda-compare-no-step",
            "eda-other-site",
            "save-gene-set",
            "export",
            "rename",
            "recap",
            "attachment",
            "frame-loop",
            "kinase-question",
            "impact",
            "assent",
            "echo",
        ]
    )


def test_a_resumed_run_reads_the_token_its_history_carries() -> None:
    calls = play("lead", "plasmodb", "", work_order="Clear it [[arc:clear]]")

    assert names(calls) == ["classify_user_intent", "clear_strategy", "final_result"]


def test_a_resumed_run_reads_the_token_of_its_newest_message() -> None:
    history: list[ModelMessage] = [
        ModelRequest(parts=[UserPromptPart(content="Build it [[arc:intersect]]")]),
        ModelRequest(
            parts=[
                UserPromptPart(
                    content="Remove it [[arc:delete-step-card]][[fault:misnamed-deletion]]"
                )
            ]
        ),
    ]

    found = contextvars.Context().run(turn_directive, history)

    assert found == ArcDirective(arc="delete-step-card", fault="misnamed-deletion")
