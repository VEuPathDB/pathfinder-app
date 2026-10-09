from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from assistant_core.errors import ModelDeclinedError
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import ToolDefinition

from pathfinder.ai.capabilities.resilience import ToolResilience
from pathfinder.platform.declined import RefusalDetails, declined_text
from pathfinder.platform.refusals import ServiceRefusalRetry
from pathfinder.tests._support.models import ANTHROPIC_STANDARD

_TAIL = (
    "These filters sometimes block legitimate research questions (false "
    "positives). Try rephrasing it, or pick a different model in Settings."
)


def test_a_model_outside_the_catalog_is_named_plainly() -> None:
    assert declined_text("function:scripted", RefusalDetails()) == (
        f"The model declined this request. Its provider's biological safety "
        f"filters blocked it. {_TAIL}"
    )


def test_a_refusal_of_another_category_names_no_biology() -> None:
    details = RefusalDetails(refusal_category="cyber")

    assert declined_text(ANTHROPIC_STANDARD, details) == (
        f"Claude Sonnet 5.5 declined this request. Its provider's safety filters "
        f"blocked it. {_TAIL}"
    )


@pytest.mark.parametrize(
    "explanation",
    ["x" * 201, "Bloqu\u00e9 for bio.", "   ", "two\nlines"],
    ids=["long", "not ascii", "blank", "two lines"],
)
def test_an_explanation_that_is_not_short_plain_text_is_left_out(
    explanation: str,
) -> None:
    details = RefusalDetails(refusal=explanation)

    assert declined_text(ANTHROPIC_STANDARD, details) == (
        f"Claude Sonnet 5.5 declined this request. Its provider's biological "
        f"safety filters blocked it. {_TAIL}"
    )


def test_a_short_plain_explanation_is_kept_stripped() -> None:
    details = RefusalDetails(refusal="  Possible bio misuse.  ")

    assert details.plain_explanation == "Possible bio misuse."


def _seam_args() -> dict[str, Any]:
    return {
        "call": ToolCallPart(tool_name="frame", args={}, tool_call_id="tc_1"),
        "tool_def": ToolDefinition(
            name="frame", description="test", parameters_json_schema={}
        ),
        "args": {},
        "error": ModelDeclinedError("declined", model_id=ANTHROPIC_STANDARD),
    }


@pytest.mark.asyncio
async def test_the_refusal_seam_does_not_retry_a_decline() -> None:
    capability: ServiceRefusalRetry[Any] = ServiceRefusalRetry()

    with pytest.raises(ModelDeclinedError):
        await capability.on_tool_execute_error(MagicMock(), **_seam_args())


@pytest.mark.asyncio
async def test_tool_resilience_does_not_retry_a_decline() -> None:
    with pytest.raises(ModelDeclinedError):
        await ToolResilience().on_tool_execute_error(MagicMock(), **_seam_args())
