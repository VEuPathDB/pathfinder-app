"""The name the suite reads off each instruction shape an agent can pin."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import InstructionPart
from pydantic_ai.models.test import TestModel
from pydantic_ai.template import TemplateStr

from pathfinder.tests._support.instructions import (
    instruction_name,
    pinned_instructions,
)


class UncompiledTemplate(TemplateStr[Any]):
    """A template whose source the optional handlebars backend never compiles."""

    def __init__(self) -> None:
        pass


def a_named_renderer() -> str:
    return "rendered at run time"


def test_a_string_instruction_is_its_own_literal() -> None:
    """A literal instruction reads back as the text it pins."""
    assert instruction_name("answer about plasmodb only") == (
        "answer about plasmodb only"
    )


def test_a_callable_instruction_is_its_function_name() -> None:
    """A renderer reads back as the name of the function that computes it."""
    assert instruction_name(a_named_renderer) == "a_named_renderer"


def test_a_named_part_is_its_declared_name() -> None:
    """A part that declares a name reads back as that name."""
    part = InstructionPart(content="tools 0/6", name="pinned_run_budget")
    assert instruction_name(part) == "pinned_run_budget"


def test_an_unnamed_part_is_its_content() -> None:
    """A part with no name reads back as its text, like a literal instruction."""
    assert instruction_name(InstructionPart(content="tools 0/6")) == "tools 0/6"


def test_a_template_instruction_names_the_shape_it_refuses() -> None:
    """A template carries no name, so the helper refuses it by shape."""
    with pytest.raises(TypeError, match="TemplateStr"):
        instruction_name(UncompiledTemplate())


def test_every_pinned_shape_reads_back_in_the_order_it_is_pinned() -> None:
    """The pinned list mixes shapes and keeps the order the agent pins them in."""
    agent: Agent[None, str] = Agent(
        TestModel(),
        instructions=[
            "answer about plasmodb only",
            InstructionPart(content="tools 0/6", name="pinned_run_budget"),
        ],
    )
    agent.instructions(a_named_renderer)

    assert pinned_instructions(agent) == [
        "answer about plasmodb only",
        "pinned_run_budget",
        "a_named_renderer",
    ]
