"""What the model sees after a branch and after a revert.

F2 and R3 of the thread-surgery invariants: a turn on the branched or reverted
thread reads the history the anchor left, so it sees the pre-anchor tool calls
and none of the post-anchor ones.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.conversation.event_writer import (
    ChatEventWriter,
    append_user_message_once,
)
from assistant_core.graph.single_agent import single_agent_graph
from assistant_core.graph.turn_state import TurnState
from assistant_core.models.scripted import (
    RoleMarkers,
    ScriptedModel,
    ScriptedPart,
    called_tool_parts,
    current_turn,
    last_user_text,
    scripted_call,
    scripted_text,
    tool_return_parts,
    user_texts,
)
from assistant_core.persistence.models import Conversation, Message
from assistant_core.persistence.repositories.message import MessagesRepository
from assistant_core.platform import db
from assistant_core.spec import AssistantSpec, TurnContextRequest
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph
from pydantic_ai import Agent, Tool
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import select

from pathfinder.ai.conversation import turn_runner
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.assistants.site_help.agent import SiteHelpDeps
from pathfinder.assistants.site_help.spec import (
    SiteHelpTurnContext,
    build_deps,
    build_initial_state,
    build_turn_context,
    charge_usage,
)
from pathfinder.persistence.models import User
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import SITE_HELP_ASSISTANT_ID
from pathfinder.services.conversations.fork import fork_conversation
from pathfinder.services.conversations.revert import revert_conversation_to_message

RECORD_TOOL = "record_finding"
FIRST_LABEL = "gametocyte-proteases"
SECOND_LABEL = "vivax-orthologs"
THIRD_LABEL = "kinase-controls"


async def record_finding(label: str) -> str:
    """Write one finding down under a label."""
    return f"recorded {label}"


@dataclass
class _Recorder:
    """Answers every run, and keeps the messages each run was handed."""

    runs: list[list[ModelMessage]] = field(default_factory=list)

    def script(self, messages: list[ModelMessage]) -> ScriptedPart:
        self.runs.append(list(messages))
        if tool_return_parts(current_turn(messages)):
            return scripted_text("Noted.")
        return scripted_call(RECORD_TOOL, {"label": last_user_text(messages)})

    def model(self) -> FunctionModel:
        return ScriptedModel(
            roles=(RoleMarkers(role="recording", markers=frozenset({RECORD_TOOL})),),
            scripts={"recording": self.script},
            unknown=self.script,
        ).as_function_model()

    def agent(self) -> Agent[SiteHelpDeps, str]:
        return Agent(
            self.model(),
            output_type=str,
            deps_type=SiteHelpDeps,
            instructions="Write down what the user reports.",
            tools=[Tool(record_finding)],
            name="recording",
            defer_model_check=True,
        )

    def labels_of_last_run(self) -> list[str]:
        """Every label the last run's history and answer name."""
        return [
            str(part.args_as_dict()["label"])
            for part in called_tool_parts(self.runs[-1])
        ]

    def prompts_of_last_run(self) -> list[str]:
        return user_texts(self.runs[-1])


@pytest.fixture
def recorder() -> _Recorder:
    return _Recorder()


@pytest.fixture
async def saver(patch_app_db_engine: None) -> AsyncIterator[AsyncPostgresSaver]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url) as opened:
        yield opened


def _spec(recorder: _Recorder, saver: BaseCheckpointSaver[Any]) -> AssistantSpec:
    def _build_graph(
        checkpointer: BaseCheckpointSaver[Any],
    ) -> CompiledStateGraph[TurnState, SiteHelpTurnContext, TurnState, TurnState]:
        return single_agent_graph(
            checkpointer=checkpointer,
            state_type=TurnState,
            context_type=SiteHelpTurnContext,
            build_agent=recorder.agent,
            build_deps=build_deps,
            charge_usage=charge_usage,
        )

    return AssistantSpec(
        assistant_id=SITE_HELP_ASSISTANT_ID,
        build_graph=_build_graph,
        build_initial_state=build_initial_state,
        build_turn_context=build_turn_context,
        build_mock_model=recorder.model,
    )


async def _seed_thread() -> tuple[UUID, UUID]:
    user_id, conversation_id = uuid4(), uuid4()
    async with db.async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Conversation(
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
                name="findings",
                assistant_id=SITE_HELP_ASSISTANT_ID,
            ),
        )
        await session.commit()
    return user_id, conversation_id


def _body(conversation_id: UUID, message_id: UUID, text: str) -> ChatRequestBody:
    return ChatRequestBody.model_validate(
        {
            "id": str(conversation_id),
            "trigger": "submit-message",
            "messages": [
                {
                    "id": str(message_id),
                    "role": "user",
                    "parts": [{"type": "text", "text": text}],
                },
            ],
            "conversationId": str(conversation_id),
            "siteId": "plasmodb",
        },
    )


@dataclass(frozen=True)
class _Turn:
    user_message_id: UUID
    assistant_message_id: UUID


async def _run_turn(
    *,
    conversation_id: UUID,
    user_id: UUID,
    text: str,
    spec: AssistantSpec,
    saver: BaseCheckpointSaver[Any],
) -> _Turn:
    """Persist the user's message the way the dispatcher does, then drive it."""
    user_message_id = uuid4()
    async with db.async_session_factory() as session:
        await MessagesRepository(session).insert_message(
            message_id=user_message_id,
            conversation_id=conversation_id,
            role="user",
            metadata={"siteId": "plasmodb", "mode": "strategy"},
        )
        await session.commit()
    await append_user_message_once(
        conversation_id=conversation_id,
        turn_id=user_message_id,
        message_id=user_message_id,
        parts=[{"type": "text", "text": text}],
    )
    async with db.async_session_factory() as session:
        conversation = await session.get(Conversation, conversation_id)
    context = await spec.build_turn_context(
        TurnContextRequest(
            conversation=conversation,
            site_id="plasmodb",
            user_id=user_id,
            memory_store=None,
            cancel_event=asyncio.Event(),
            phase_models={},
            phase_reasoning={},
            tool_sources={},
        ),
    )
    turn_id = uuid4()
    await turn_runner._run_turn_with_context(
        request=turn_runner.TurnRequest(
            body=_body(conversation_id, user_message_id, text),
            user_id=user_id,
        ),
        spec=spec,
        compiled_graph=spec.build_graph(saver),
        runtime_context=context,
        writer=ChatEventWriter(conversation_id=conversation_id, turn_id=turn_id),
    )
    return _Turn(user_message_id=user_message_id, assistant_message_id=turn_id)


@pytest.fixture(autouse=True)
def _no_title_and_no_cancel_watch(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_poll(**_kwargs: Any) -> None:
        return None

    async def _no_title(*_args: Any, **_kwargs: Any) -> str:
        return ""

    monkeypatch.setattr(turn_runner, "watch_for_cancel", _no_poll)
    monkeypatch.setattr(turn_runner, "charged_conversation_title", _no_title)


async def _assistant_message_ids(conversation_id: UUID) -> list[str]:
    async with db.async_session_factory() as session:
        return [
            str(mid)
            for mid in (
                await session.execute(
                    select(Message.id)
                    .where(
                        Message.conversation_id == conversation_id,
                        Message.role == "assistant",
                    )
                    .order_by(Message.created_at),
                )
            ).scalars()
        ]


async def test_the_thread_carries_its_tool_calls_into_the_next_turn(
    patch_app_db_engine: None,
    db_cleaner: None,
    recorder: _Recorder,
    saver: AsyncPostgresSaver,
) -> None:
    """The baseline the branch is measured against."""
    del patch_app_db_engine, db_cleaner
    spec = _spec(recorder, saver)
    user_id, conversation_id = await _seed_thread()

    await _run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        text=FIRST_LABEL,
        spec=spec,
        saver=saver,
    )
    await _run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        text=SECOND_LABEL,
        spec=spec,
        saver=saver,
    )

    assert recorder.labels_of_last_run() == [FIRST_LABEL, SECOND_LABEL]
    assert recorder.prompts_of_last_run() == [FIRST_LABEL, SECOND_LABEL]


async def test_f2_a_turn_on_a_branch_sees_the_anchor_s_history_and_no_more(
    patch_app_db_engine: None,
    db_cleaner: None,
    recorder: _Recorder,
    saver: AsyncPostgresSaver,
) -> None:
    del patch_app_db_engine, db_cleaner
    spec = _spec(recorder, saver)
    user_id, conversation_id = await _seed_thread()
    first = await _run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        text=FIRST_LABEL,
        spec=spec,
        saver=saver,
    )
    second_answer = await _run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        text=SECOND_LABEL,
        spec=spec,
        saver=saver,
    )
    assert await _assistant_message_ids(conversation_id) == [
        str(first.assistant_message_id),
        str(second_answer.assistant_message_id),
    ]

    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=conversation_id,
            from_message_id=first.assistant_message_id,
            user_id=user_id,
        )
        await session.commit()
        fork_id = fork.id

    await _run_turn(
        conversation_id=fork_id,
        user_id=user_id,
        text=THIRD_LABEL,
        spec=spec,
        saver=saver,
    )

    assert recorder.labels_of_last_run() == [FIRST_LABEL, THIRD_LABEL]
    assert recorder.prompts_of_last_run() == [FIRST_LABEL, THIRD_LABEL]
    assert SECOND_LABEL not in recorder.labels_of_last_run()


async def test_r3_a_turn_after_a_revert_sees_the_target_s_history_and_no_more(
    patch_app_db_engine: None,
    db_cleaner: None,
    recorder: _Recorder,
    saver: AsyncPostgresSaver,
) -> None:
    del patch_app_db_engine, db_cleaner
    spec = _spec(recorder, saver)
    user_id, conversation_id = await _seed_thread()
    await _run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        text=FIRST_LABEL,
        spec=spec,
        saver=saver,
    )
    second = await _run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        text=SECOND_LABEL,
        spec=spec,
        saver=saver,
    )

    async with db.async_session_factory() as session:
        await revert_conversation_to_message(
            session,
            conversation_id=conversation_id,
            target_message_id=second.user_message_id,
            user_id=user_id,
        )
        await session.commit()

    await _run_turn(
        conversation_id=conversation_id,
        user_id=user_id,
        text=THIRD_LABEL,
        spec=spec,
        saver=saver,
    )

    assert recorder.labels_of_last_run() == [FIRST_LABEL, THIRD_LABEL]
    assert recorder.prompts_of_last_run() == [FIRST_LABEL, THIRD_LABEL]
    assert SECOND_LABEL not in recorder.labels_of_last_run()
