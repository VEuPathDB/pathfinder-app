"""The shape a tool declares, read off the value its ToolReturn carries."""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter, ValidationError
from pydantic_ai.messages import ToolReturn, ToolReturnPart


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


def wire_size[T](result: ToolReturn[T], tool_name: str) -> int:
    """The bytes the model reads, as the tool return part serializes them."""
    part = ToolReturnPart(tool_name=tool_name, content=result.return_value)
    return len(part.model_response_str().encode())
