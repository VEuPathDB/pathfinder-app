from __future__ import annotations

from pydantic_ai.messages import ToolCallPart, ToolReturnPart


def refused_reply(call: ToolCallPart, refusal: str) -> ToolReturnPart:
    return ToolReturnPart(
        content=refusal,
        tool_name=call.tool_name,
        tool_call_id=call.tool_call_id,
        outcome="retried" if call.tool_name == "final_result" else "failed",
    )
