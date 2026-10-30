"""How a turn that dies is closed, and what the researcher is told about it.

The exception is a defect report and goes to the log. The reply says whether
the turn ran and what the researcher can do next.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from assistant_core.conversation.event_writer import ChatWriter
from assistant_core.graph.stream_events import turn_failed_event
from assistant_core.platform.logging import get_logger
from pydantic_ai.ui.vercel_ai.response_types import (
    DoneChunk,
    ErrorChunk,
    FinishChunk,
)

from pathfinder.platform.errors import AppError
from pathfinder.services.site_errors import SiteDidNotAnswerError, unanswered_site

logger = get_logger(__name__)

# What a dead turn tells the researcher. This module closes the turn of every
# assistant, so the sentences name nothing an assistant may not have. A turn
# that died before the graph ran wrote nothing; a turn that died inside it
# claims neither, unless its failure says that it changed nothing.
STOPPED_BEFORE_IT_RAN = (
    "This turn stopped before it could start, so nothing was changed. "
    "Send the message again."
)
STOPPED_WHILE_RUNNING = "This turn stopped before it could answer. Ask again."


def turn_failure_text(exc: Exception, *, graph_ran: bool) -> str:
    """What the researcher reads when this turn dies.

    A typed refusal already carries its own sentence, and a site that did not
    answer is named. Any other failure is a defect, whose type and message go
    to the log alone.
    """
    match exc:
        case AppError():
            return exc.detail or exc.title
        case SiteDidNotAnswerError():
            return _unanswered(exc.site.name, ran=graph_ran and not exc.changed_nothing)
    site = unanswered_site(exc)
    if site is not None:
        return _unanswered(site.name, ran=graph_ran)
    return STOPPED_WHILE_RUNNING if graph_ran else STOPPED_BEFORE_IT_RAN


def _unanswered(site_name: str, *, ran: bool) -> str:
    if ran:
        return (
            f"{site_name} did not answer, so this turn stopped before it could "
            "answer. Ask again."
        )
    return (
        f"{site_name} did not answer, so this turn stopped and nothing was "
        "changed. Send the message again."
    )


async def write_turn_failure(writer: ChatWriter, exc: Exception) -> None:
    """Close a turn that failed before its graph ran, the way a graph failure closes."""
    logger.error(
        "Turn failed before the graph ran",
        exc_info=exc,
        conversation_id=str(writer.conversation_id),
        error_type=type(exc).__name__,
        error_detail=str(exc),
    )
    error_text = turn_failure_text(exc, graph_ran=False)
    for chunk in (
        ErrorChunk(error_text=error_text),
        turn_failed_event(error_text=error_text),
        FinishChunk(finish_reason="error"),
        DoneChunk(),
    ):
        await writer.write(
            chunk.model_dump(by_alias=True, mode="json", exclude_none=True)
        )


@contextlib.asynccontextmanager
async def turn_closed_on_failure(writer: ChatWriter) -> AsyncIterator[None]:
    """A setup step that raises inside still ends the turn on the wire."""
    try:
        yield
    except Exception as exc:
        await write_turn_failure(writer, exc)
        raise
