from __future__ import annotations

from functools import partial
from typing import Any, Literal
from uuid import UUID

from assistant_core.graph.emit import emit_chunk
from assistant_core.graph.stream_events import scratchpad_updated_event
from assistant_core.graph.turn_message import write_turn_message
from assistant_core.memory.deadline import memory_store_deadline
from assistant_core.memory.store import MemoryStore
from assistant_core.memory.tombstones import TombstoneRepository
from assistant_core.platform.logging import get_logger
from assistant_core.scratchpad.compactor import compact_scratchpad
from langgraph.runtime import Runtime
from langgraph.types import Command
from sqlalchemy.exc import SQLAlchemyError

from pathfinder.ai.agents.compactor import build_compactor_agent
from pathfinder.ai.capabilities.metering import SpendMeter, charge_spend
from pathfinder.ai.graph._lead_capture import turn_with_spend
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.memory_candidates import collect_turn_memory_candidates
from pathfinder.domain.strategy.build_outcome import built_counts
from pathfinder.services.conversations.message_ratings import (
    TurnMemories,
    write_turn_memories,
)
from pathfinder.services.conversations.turns import name_turn_strategy_revision

logger = get_logger(__name__)

_END: Literal["__end__"] = "__end__"


async def _name_strategy_revision(
    *,
    context: Context,
    conversation_id: UUID,
    message_id: UUID,
) -> None:
    """Name the turn's strategy snapshot. A database refusal does not fail the turn."""
    try:
        await name_turn_strategy_revision(
            context.db_session_factory,
            conversation_id=conversation_id,
            message_id=message_id,
        )
    except SQLAlchemyError:
        logger.warning(
            "failed to name the turn's strategy revision",
            conversation_id=str(conversation_id),
        )


async def _compact_the_notes(
    context: Context, state: PipelineState, writer: Any
) -> PipelineState:
    """Compact the thread's notes, charging the run to its payer and to the turn.

    A failed compaction does not fail the turn; what its run spent is charged.
    """
    meter = SpendMeter()
    try:
        compaction_run = await compact_scratchpad(
            conversation_id=state.conversation_id,
            db_session_factory=context.db_session_factory,
            agent=partial(build_compactor_agent, meter=meter),
        )
    except Exception:
        logger.exception(
            "scratchpad compaction failed",
            conversation_id=str(state.conversation_id),
        )
        compaction_run = None
    await charge_spend(
        context.db_session_factory, user_id=state.user_id, spent=meter.spent
    )
    if compaction_run is not None:
        emit_chunk(writer, scratchpad_updated_event())
    return turn_with_spend(state, meter, writer)


async def _write_the_notes(
    context: Context, state: PipelineState, *, turn_message_id: UUID | None
) -> bool:
    """Write the turn's memories. Returns whether they were written.

    The reply is on the wire before this runs, so a failure here is logged and
    the turn ends as it would without the notes.
    """
    if context.memory_store is None:
        return False
    try:
        session = context.strategy_session
        candidates = await collect_turn_memory_candidates(
            state, counts=built_counts(session.get_graph(None), session.sync_state)
        )
        async with memory_store_deadline("the memory auto-write"):
            await write_turn_memories(
                TurnMemories(
                    user_id=state.user_id,
                    conversation_id=state.conversation_id,
                    message_id=turn_message_id,
                    candidates=candidates,
                ),
                session_factory=context.db_session_factory,
                store=MemoryStore(store=context.memory_store),
                tombstones=TombstoneRepository(
                    session_factory=context.db_session_factory,
                ),
            )
    except Exception:
        logger.exception(
            "the memory auto-write failed; the turn keeps its reply",
            conversation_id=str(state.conversation_id),
        )
        return False
    return True


async def finalize_turn_node(
    state: PipelineState, runtime: Runtime[Context]
) -> Command[Literal["__end__"]]:
    verdict = state.checked_verdict
    update: dict[str, object] = {}
    if runtime.context is not None and verdict is not None:
        compacted = await _compact_the_notes(
            runtime.context, state, runtime.stream_writer
        )
        if compacted is not state:
            update["turn_total_tokens"] = compacted.turn_total_tokens
            update["turn_total_cost_usd"] = compacted.turn_total_cost_usd
        state = compacted

    turn_message_id: UUID | None = None
    if runtime.context is not None:
        turn_message_id = await write_turn_message(
            context=runtime.context,
            state=state,
        )
        if turn_message_id is not None:
            await _name_strategy_revision(
                context=runtime.context,
                conversation_id=state.conversation_id,
                message_id=turn_message_id,
            )

    notes_written = False
    if runtime.context is not None and verdict is not None and verdict.passed:
        notes_written = await _write_the_notes(
            runtime.context, state, turn_message_id=turn_message_id
        )

    if notes_written and state.domain.created_gene_sets:
        # A note in the store is not offered again, so the per-turn write does
        # not grow with the thread.
        update["domain"] = state.domain.model_copy(update={"created_gene_sets": []})
    return Command(goto=_END, update=update or None)
