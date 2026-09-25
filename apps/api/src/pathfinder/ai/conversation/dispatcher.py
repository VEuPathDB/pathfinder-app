from __future__ import annotations

from uuid import UUID, uuid4

from assistant_core.conversation.cancellation import cancel_in_flight_turn
from assistant_core.conversation.event_stream import (
    iter_sse,
    latest_turn_boundary,
)
from assistant_core.conversation.event_writer import (
    ChatEventWriter,
    append_user_message_once,
)
from assistant_core.conversation.vercel_adapter import VERCEL_AI_DSP_HEADERS
from assistant_core.graph.stream_events import turn_status_event
from assistant_core.persistence.repositories.message import MessagesRepository
from assistant_core.spec import AssistantSpec
from assistant_core.tasks.chat_turn import defer_chat_turn
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.capabilities.security import scan_user_input
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.jobs.payloads import ChatTurnPayload
from pathfinder.platform.errors import AssistantMismatchError
from pathfinder.services.conversations.begin import begin_conversation


async def dispatch(
    *,
    body: ChatRequestBody,
    session: AsyncSession,
    user_id: UUID,
    spec: AssistantSpec,
) -> Response:
    """Scan user input, persist it, enqueue a turn job, tail the event stream.

    Two trigger modes:

    - Normal turn: ``messages[-1]`` is a user message -> persist + chunk it.
    - Approval resume: SDK v6 fired the request after
      ``chat.addToolApprovalResponse`` (no new user message) - skip the
      user-message persistence and chunk; the worker reads
      ``state.approval_responses`` from the request body and resumes the
      deferred tool.
    """
    begun = await begin_conversation(
        session=session,
        conversation_id=body.conversation_id,
        user_id=user_id,
        site_id=body.site_id,
        assistant_id=spec.assistant_id,
    )
    # The row is the authority. A concurrent first turn can create the thread
    # under another assistant between the resolve and the insert.
    if begun.conversation.assistant_id != spec.assistant_id:
        raise AssistantMismatchError(
            requested=spec.assistant_id,
            existing=begun.conversation.assistant_id,
        )

    if not body.is_approval_resume:
        await cancel_in_flight_turn(body.conversation_id)
        await scan_user_input(body.last_user_text)

        await MessagesRepository(session).insert_message(
            message_id=body.last_user_message_id,
            conversation_id=body.conversation_id,
            role="user",
            metadata={"siteId": body.site_id, "mode": body.mode},
        )
        await session.commit()

        # A regenerate sends the thread back ending at the same user message.
        # The log carries that message once, because a client rebuilds its
        # thread from the log and one id names one message.
        await append_user_message_once(
            conversation_id=body.conversation_id,
            turn_id=body.last_user_message_id,
            message_id=body.last_user_message_id,
            parts=body.last_user_parts,
        )

    after = await latest_turn_boundary(body.conversation_id)

    turn_id = body.prior_assistant_message_id or uuid4()
    payload = ChatTurnPayload.from_context(
        body=body,
        user_id=user_id,
        turn_id=turn_id,
        assistant_id=spec.assistant_id,
    )
    # The status is persisted before the job exists, so it can never land after
    # the worker's first chunk.
    await ChatEventWriter(
        conversation_id=body.conversation_id,
        turn_id=turn_id,
    ).write(
        turn_status_event(label="Queued").model_dump(
            by_alias=True,
            mode="json",
            exclude_none=True,
        ),
    )
    await defer_chat_turn(
        conversation_id=body.conversation_id,
        payload=payload.model_dump(mode="json", by_alias=True),
    )

    return StreamingResponse(
        iter_sse(conversation_id=body.conversation_id, after=after),
        media_type="text/event-stream",
        headers=dict(VERCEL_AI_DSP_HEADERS),
    )


__all__ = ["ChatRequestBody", "dispatch"]
