from __future__ import annotations

from typing import Literal
from uuid import UUID

from assistant_core.graph.emit import emit_chunk
from assistant_core.graph.stream_events import scratchpad_updated_event
from assistant_core.graph.turn_message import write_turn_message
from assistant_core.memory.deadline import (
    MemoryStoreTimeoutError,
    memory_store_deadline,
)
from assistant_core.memory.store import MemoryStore
from assistant_core.memory.tombstones import TombstoneRepository
from assistant_core.platform.logging import get_logger
from assistant_core.scratchpad.compactor import compact_scratchpad
from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime
from langgraph.types import Command
from sqlalchemy.exc import SQLAlchemyError

from pathfinder.ai.agents.compactor import build_compactor_agent
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.memory_candidates import collect_turn_memory_candidates
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


async def finalize_turn_node(
    state: PipelineState, runtime: Runtime[Context]
) -> Command[Literal["__end__"]]:
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

    # A verdict stands while the strategy is the one it judged, so only the
    # turn that ran the check treats it as this turn's finding.
    notes_written = False
    checked = state.turn_markers.verification_dispatched
    verdict = state.turn_verdict if checked else None
    if (
        runtime.context is not None
        and verdict is not None
        and verdict.passed
        and runtime.context.memory_store is not None
    ):
        try:
            candidates = await collect_turn_memory_candidates(state)
            async with memory_store_deadline("the memory auto-write"):
                await write_turn_memories(
                    TurnMemories(
                        user_id=state.user_id,
                        conversation_id=state.conversation_id,
                        message_id=turn_message_id,
                        candidates=candidates,
                    ),
                    session_factory=runtime.context.db_session_factory,
                    store=MemoryStore(store=runtime.context.memory_store),
                    tombstones=TombstoneRepository(
                        session_factory=runtime.context.db_session_factory,
                    ),
                )
            notes_written = True
        except MemoryStoreTimeoutError as exc:
            logger.exception(
                "the memory auto-write timed out; the turn fails",
                conversation_id=str(state.conversation_id),
                seconds=exc.seconds,
            )
            raise
        except (RuntimeError, ValueError, OSError, SQLAlchemyError) as exc:
            logger.warning("auto-write memories failed: %s", exc)

    if runtime.context is not None and verdict is not None:
        try:
            compaction_run = await compact_scratchpad(
                conversation_id=state.conversation_id,
                db_session_factory=runtime.context.db_session_factory,
                agent=build_compactor_agent,
            )
        except Exception:
            logger.exception(
                "scratchpad compaction failed",
                conversation_id=str(state.conversation_id),
            )
            compaction_run = None
        if compaction_run is not None:
            emit_chunk(get_stream_writer(), scratchpad_updated_event())

    if notes_written and state.domain.created_gene_sets:
        # A note in the store is not offered again, so the per-turn write does
        # not grow with the thread.
        kept = state.domain.model_copy(update={"created_gene_sets": []})
        return Command(goto=_END, update={"domain": kept})
    return Command(goto=_END)
