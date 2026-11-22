"""A refused parameter value reaches the model as the validator states it."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from strategist.ai.agents.tool_vocabulary import SEARCH_LOOKUP_TOOLS
from strategist.ai.capabilities.resilience import ToolResilience

from .test_resilience import _make_call, _make_ctx, _make_tool_def


class _ArgsModel(BaseModel):
    step_id: str
    parameters: dict[str, dict[str, Any]]


async def test_a_parameter_value_error_asks_for_no_wrapper() -> None:
    args = {"step_id": "a", "parameters": {"organism": ["Pf3D7"]}}
    with pytest.raises(ValidationError) as caught:
        _ArgsModel.model_validate(args)

    with pytest.raises(ValidationError):
        await ToolResilience(
            search_lookup_tools=SEARCH_LOOKUP_TOOLS
        ).on_tool_validate_error(
            _make_ctx(),
            call=_make_call("update_leaf_params"),
            tool_def=_make_tool_def("update_leaf_params"),
            args=args,
            error=caught.value,
        )
