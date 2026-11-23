from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from assistant_core.capabilities.repetition_guard import (
    RepetitionGuard,
    ToolRepetitionGuard,
)
from pydantic_ai import AgentRunResultEvent
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.messages import (
    AgentStreamEvent,
    ModelMessage,
    ModelResponse,
    ToolCallPart,
    UserContent,
)
from pydantic_ai.tools import DeferredToolResults
from pydantic_ai.usage import RunUsage, UsageLimits

from strategist.ai.graph._lead_capture import LeadRunCapture, _charge_token_delta
from strategist.ai.graph._lead_events import handle_sub_agent_event
from strategist.ai.graph._lead_result import absorb_run_result, ask_about_what_it_parks
from strategist.ai.graph._lead_stops import guard_stop_of
from strategist.ai.graph.state import PipelineState
from strategist.ai.lead.lead_agent import LeadAgent
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.lead.turn_budget import lead_token_budget
from strategist.ai.lead.turn_contract import LeadResponse
from strategist.ai.lead.turn_record import owes_a_check

RUNTIME_CHECK = (
    "The runtime checks the strategy this turn changed before the reply. Write "
    "the reply from this check's verdict and its stops."
)


def the_runtime_check(
    deps: LeadDeps, result: AgentRunResult[Any]
) -> list[ModelMessage] | None:
    """The answered run with the check the runtime makes in the Lead's place,
    or None when the answer owes no check."""
    match result.output:
        case LeadResponse() if owes_a_check(deps):
            return [
                *result.all_messages(),
                ModelResponse(
                    parts=[
                        ToolCallPart(
                            tool_name="verify_strategy",
                            args={"reason": RUNTIME_CHECK},
                            tool_call_id=f"call_runtime_check_{uuid4().hex[:12]}",
                        )
                    ]
                ),
            ]
        case _:
            return None


def stream_ends_after(
    event: AgentStreamEvent | AgentRunResultEvent[Any],
    guard: ToolRepetitionGuard,
    capture: LeadRunCapture,
) -> bool:
    """Whether this event is the last one the turn takes from the run."""
    stop = guard_stop_of(event, guard)
    if stop is None:
        return False
    capture.guard_stop = stop
    return True


@dataclass
class LeadRuns:
    agent: LeadAgent
    deps: LeadDeps
    state: PipelineState
    capture: LeadRunCapture
    writer: Any
    limits: UsageLimits
    usage: RunUsage
    model_id: str
    tool_calls: dict[str, str]
    finished: list[AgentRunResult[Any]] = field(default_factory=list)

    def check_owed(self) -> list[ModelMessage] | None:
        if self.capture.guard_stop is not None or not self.finished:
            return None
        return the_runtime_check(self.deps, self.finished[-1])

    async def events(
        self,
        prompt: str | Sequence[UserContent] | None,
        history: list[ModelMessage] | None,
        results: DeferredToolResults | None,
    ) -> AsyncGenerator[AgentStreamEvent | AgentRunResultEvent[Any]]:
        deps, capture = self.deps, self.capture
        guard = deps.tool_repetition_guard
        async with self.agent.run_stream_events(
            prompt,
            deps=deps,
            message_history=history,
            deferred_tool_results=results,
            capabilities=[RepetitionGuard(guard=guard), lead_token_budget()],
            usage_limits=self.limits,
            usage=self.usage,
        ) as events:
            async for event in events:
                capture.note_model_output(event)
                if isinstance(event, AgentRunResultEvent):
                    self.finished.append(event.result)
                    absorb_run_result(event, capture, deps)
                    await ask_about_what_it_parks(event, deps, self.writer)
                else:
                    handle_sub_agent_event(
                        deps,
                        self.writer,
                        event,
                        self.tool_calls,
                        capture.sub_agent_usage_by_call,
                    )
                await _charge_token_delta(
                    deps.runtime,
                    self.state,
                    capture,
                    self.usage,
                    self.writer,
                    self.model_id,
                )
                yield event
                if stream_ends_after(event, guard, capture):
                    return
