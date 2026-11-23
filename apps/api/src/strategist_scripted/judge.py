from __future__ import annotations

from typing import Final

from assistant_core.models.scripted import last_user_text, terminal_call
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel

INJECTION_TEST_MARKER: Final = "[[strategist-injection-test]]"


def injection_judge() -> FunctionModel:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        injected = INJECTION_TEST_MARKER in last_user_text(messages)
        return ModelResponse(
            parts=[terminal_call({"injection": injected, "confidence": 1.0})],
        )

    return FunctionModel(respond, model_name="mock:injection-judge")
