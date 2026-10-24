from __future__ import annotations

from dataclasses import dataclass

from assistant_core.graph.tool_summary import count_noun
from pydantic_ai.capabilities.abstract import AbstractCapability, AgentNode, NodeResult
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    repair_messages,
)
from pydantic_ai.result import FinalResult
from pydantic_ai.tools import RunContext
from pydantic_graph import End

from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.reply import AuditReply


def budget_stop_prose(recorded: int) -> str:
    return (
        "I stopped this turn at its limit of model requests and tool calls, before I "
        f"finished. I stored {count_noun(recorded, 'verdict')} in this turn, and each "
        "one is kept. Ask me to go on and I judge the findings that have no verdict "
        "yet."
    )


def _last_response(messages: list[ModelMessage]) -> ModelResponse:
    for message in reversed(messages):
        match message:
            case ModelResponse():
                return message
            case _:
                continue
    return ModelResponse(parts=[])


def _stopped(messages: list[ModelMessage], prose: str) -> list[ModelMessage]:
    last = _last_response(messages)
    reply = ModelResponse(
        parts=[TextPart(prose)],
        model_name=last.model_name,
        provider_name=last.provider_name,
        provider_url=last.provider_url,
    )
    return [*repair_messages(messages), reply]


@dataclass
class StopAtTheBudget(AbstractCapability[AuditDeps]):
    async def on_node_run_error(
        self,
        ctx: RunContext[AuditDeps],
        *,
        node: AgentNode[AuditDeps],
        error: Exception,
    ) -> NodeResult[AuditDeps]:
        del node
        match error:
            case UsageLimitExceeded():
                reply = AuditReply(prose=budget_stop_prose(len(ctx.deps.recorded)))
                ctx.messages[:] = _stopped(ctx.messages, reply.prose)
                return End(FinalResult(reply))
            case _:
                raise error
