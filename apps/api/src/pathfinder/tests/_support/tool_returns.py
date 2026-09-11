"""The shape a tool declares, read off the value its ToolReturn carries."""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter, ValidationError
from pydantic_ai.messages import ToolReturn


def returned[T](result: ToolReturn[Any], shape: type[T]) -> T:
    """Read a tool return value as the shape the tool declares.

    `ToolReturn.return_value` is a wide union, so a test that asserts on a
    field binds the declared shape here first.
    """
    try:
        return TypeAdapter(shape).validate_python(result.return_value)
    except ValidationError as error:
        actual = type(result.return_value).__name__
        msg = f"the tool returned {actual}, not {shape}"
        raise AssertionError(msg) from error


def summary_text(result: ToolReturn[Any]) -> str:
    """Read the summary line a tool writes beside its return value.

    `ToolReturn.content` is a wide union, so a test that asserts on the line
    binds the text here first.
    """
    try:
        return TypeAdapter(str).validate_python(result.content)
    except ValidationError as error:
        actual = type(result.content).__name__
        msg = f"the tool wrote {actual} as its summary, not text"
        raise AssertionError(msg) from error
