"""How this application runs the turn a finished durable task opens.

The runtime reads the parked call and gathers the answers; this turns that
into the request body a PathFinder turn runs under.
"""

from __future__ import annotations

from assistant_core.tasks.completion_turn import CompletionTurn

from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.ai.conversation.turn_runner import TurnRequest, run_turn
from pathfinder.jobs.turn_keys import turn_keys


async def open_completion_turn(turn: CompletionTurn) -> None:
    """Re-enter the run that deferred the durable calls, under its own picks."""
    body = ChatRequestBody.model_validate(
        {
            "conversation_id": turn.conversation_id,
            "phase_models": turn.phase_overrides.models,
            "phase_reasoning": turn.phase_overrides.reasoning,
        },
    )
    async with turn_keys(
        user_id=turn.user_id, spec=turn.spec, body=body, writer=turn.writer
    ):
        await run_turn(
            request=TurnRequest(
                body=body,
                user_id=turn.user_id,
                durable_result=turn.durable_result,
                durable_results=turn.durable_results,
            ),
            spec=turn.spec,
            compiled_graph=turn.compiled_graph,
            memory_store=turn.memory_store,
            writer=turn.writer,
        )


__all__ = ["open_completion_turn"]
