"""The value a strategy step's parameter carries, read at the shape it holds."""

from __future__ import annotations

from pydantic import TypeAdapter, ValidationError
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode


def string_param(node: StrategyStepNode, name: str) -> str:
    """Read one parameter of a step as the text a string parameter holds.

    `StrategyStepNode.parameters` holds the whole parameter-value union, so a
    test that asserts on text binds the string shape here first.
    """
    value = node.parameters[name]
    try:
        return TypeAdapter(StringValue).validate_python(value).value
    except ValidationError as error:
        msg = f"parameter {name} holds {type(value).__name__}, not StringValue"
        raise AssertionError(msg) from error
