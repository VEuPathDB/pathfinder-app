"""What an agent pins as instructions, in the order it pins them."""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent
from pydantic_ai._instructions import AgentInstruction
from pydantic_ai.messages import InstructionPart
from pydantic_ai.template import TemplateStr


def instruction_name(instruction: AgentInstruction[Any]) -> str:
    """The name of one instruction, or its literal text when it carries no name."""
    match instruction:
        case str():
            return instruction
        case InstructionPart(name=str() as name):
            return name
        case InstructionPart(content=content):
            return content
        case TemplateStr():
            msg = "a TemplateStr instruction carries no name"
            raise TypeError(msg)
        case _:
            return instruction.__name__


def pinned_instructions(agent: Agent[Any, Any]) -> list[str]:
    """Each pinned instruction as its literal text, or as its renderer name."""
    return [instruction_name(sourced.instruction) for sourced in agent._instructions]
