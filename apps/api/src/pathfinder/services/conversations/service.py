"""Conversation CRUD service.

Owns conversation read/write orchestration (repository + WDK sync + response
shaping) so transport routers stay thin and never import persistence.
"""

from dataclasses import dataclass
from uuid import UUID, uuid4

from assistant_core.conversation.authz import (
    get_owned_conversation,
    get_visible_conversation,
)
from assistant_core.conversation.cancellation import stop_turn_before_delete
from assistant_core.persistence.repositories.message import MessagesRepository
from assistant_core.platform.logging import get_logger
from assistant_core.platform.types import JSONObject
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy.operations import GraphOperation
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.strategy_ast import (
    StrategyAst,
)
from veupathdb.domain.strategy.tree import walk
from veupathdb.errors import ValidationError, VEuPathDBError
from veupathdb.wdk.factory import get_strategy_api

from pathfinder.persistence.models import ConversationStrategy
from pathfinder.persistence.repositories import (
    ConversationRepository,
    ConversationUpdate,
)
from pathfinder.platform.errors import ErrorCode, NotFoundError
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.conversations import strategy_ops
from pathfinder.services.conversations.authz import get_owned_thread_or_404
from pathfinder.services.conversations.begin import begin_conversation
from pathfinder.services.conversations.fork import ForkError, fork_conversation
from pathfinder.services.conversations.responses import (
    ConversationResponse,
    build_conversation_response,
    build_conversation_summaries,
    build_conversation_summary,
)
from pathfinder.services.strategies.insert_saved import (
    InsertSavedResult,
)
from pathfinder.services.strategies.plan_validation import validate_plan_or_raise
from pathfinder.services.strategies.save_substrategy import (
    SavedSubstrategyResult,
)
from pathfinder.services.strategies.wdk_sync import (
    lazy_fetch_wdk_detail,
    sync_is_saved_to_wdk,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class BegunConversation:
    conversation_id: UUID
    is_new: bool
    name: str


@dataclass(frozen=True)
class DuplicatedConversation:
    id: UUID
    name: str


@dataclass(frozen=True)
class ConversationUpdateInput:
    name: str | None
    strategy_ast: StrategyAst | None
    wdk_strategy_id: int | None
    wdk_strategy_id_set: bool
    is_saved: bool | None
    is_saved_set: bool


class ConversationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ConversationRepository(session)

    async def list_active(
        self,
        user_id: UUID,
        site_id: str | None,
    ) -> list[ConversationResponse]:
        rows = await self._repo.list_conversations(user_id, site_id)
        return build_conversation_summaries(rows, site_id=site_id or "")

    async def list_dismissed(
        self,
        user_id: UUID,
        site_id: str | None,
    ) -> list[ConversationResponse]:
        rows = await self._repo.list_dismissed_conversations(user_id, site_id)
        return build_conversation_summaries(rows, site_id=site_id or "")

    async def create(
        self,
        *,
        user_id: UUID,
        site_id: str,
        name: str,
        strategy_ast: StrategyAst,
    ) -> ConversationResponse:
        payload = validate_plan_or_raise(strategy_ast.model_dump(exclude_none=True))
        conversation = await self._repo.create(
            user_id=user_id,
            site_id=site_id,
            assistant_id=PATHFINDER_ASSISTANT_ID,
            name=name,
        )
        await self._repo.update_conversation(
            conversation.id,
            ConversationUpdate(
                strategy_ast=payload,
                record_type=payload.record_type,
                step_count=len(walk(payload.root)),
            ),
        )
        refreshed = await self._repo.get_with_strategy(conversation.id)
        if not refreshed:
            raise NotFoundError(
                code=ErrorCode.STRATEGY_NOT_FOUND,
                title="Strategy not found",
            )
        return build_conversation_response(*refreshed)

    async def get_detail(
        self, conversation_id: UUID, user_id: UUID
    ) -> ConversationResponse:
        conversation, strategy = await get_owned_thread_or_404(
            self._repo,
            conversation_id,
            user_id,
        )
        conversation, strategy = await lazy_fetch_wdk_detail(
            conversation=conversation,
            strategy=strategy,
            conv_repo=self._repo,
        )
        total_tokens, total_cost = await MessagesRepository(
            self._session,
        ).sum_usage_for_conversation(conversation.id)
        return build_conversation_response(
            conversation,
            strategy,
            total_tokens=total_tokens,
            total_cost_usd=total_cost,
        )

    async def update(
        self,
        conversation_id: UUID,
        user_id: UUID,
        patch: ConversationUpdateInput,
    ) -> ConversationResponse:
        await get_owned_conversation(self._repo, conversation_id, user_id)

        payload: StrategyAst | None = None
        record_type: str | None = None
        if patch.strategy_ast:
            payload = validate_plan_or_raise(
                patch.strategy_ast.model_dump(exclude_none=True),
            )
            record_type = payload.record_type

        await self._repo.update_conversation(
            conversation_id,
            ConversationUpdate(
                name=patch.name,
                strategy_ast=payload,
                record_type=record_type,
                wdk_strategy_id=patch.wdk_strategy_id,
                wdk_strategy_id_set=patch.wdk_strategy_id_set,
                is_saved=patch.is_saved,
                is_saved_set=patch.is_saved_set,
                step_count=len(walk(payload.root)) if payload else None,
            ),
        )
        found = await self._repo.get_with_strategy(conversation_id)
        if not found:
            raise NotFoundError(
                code=ErrorCode.STRATEGY_NOT_FOUND,
                title="Strategy not found",
            )
        updated, strategy = found
        if patch.is_saved_set and strategy.wdk_strategy_id:
            await sync_is_saved_to_wdk(conversation=updated, strategy=strategy)
        return build_conversation_response(updated, strategy)

    async def fork(
        self,
        conversation_id: UUID,
        user_id: UUID,
        from_message_id: UUID,
    ) -> ConversationResponse:
        await get_owned_conversation(self._repo, conversation_id, user_id)
        try:
            fork = await fork_conversation(
                self._session,
                source_conversation_id=conversation_id,
                from_message_id=from_message_id,
                user_id=user_id,
            )
        except ForkError as exc:
            raise NotFoundError(
                code=ErrorCode.STRATEGY_NOT_FOUND,
                title=str(exc),
            ) from exc
        await self._session.commit()
        refreshed = await self._repo.get_with_strategy(fork.id)
        if refreshed is None:
            raise NotFoundError(
                code=ErrorCode.STRATEGY_NOT_FOUND,
                title="Strategy not found",
            )
        return build_conversation_summary(*refreshed, site_id=refreshed[0].site_id)

    async def delete(
        self,
        conversation_id: UUID,
        user_id: UUID,
        *,
        delete_from_wdk: bool,
        cascade: bool,
    ) -> None:
        conversation, strategy = await get_owned_thread_or_404(
            self._repo,
            conversation_id,
            user_id,
        )
        wdk_id = strategy.wdk_strategy_id
        is_wdk_linked = wdk_id is not None

        if is_wdk_linked and delete_from_wdk and wdk_id is not None:
            consumers = await strategy_ops.list_saved_strategy_consumers(
                self._repo, user_id, wdk_id, exclude_conversation_id=conversation_id
            )
            if consumers:
                consumer_names = ", ".join(c.name for c in consumers[:5])
                raise ValidationError(
                    title="saved strategy still in use",
                    detail=(
                        f"{len(consumers)} other conversation(s) import this saved "
                        f"strategy: {consumer_names}"
                    ),
                )

        if is_wdk_linked and not delete_from_wdk:
            await self._repo.dismiss(conversation_id)
            await self._session.commit()
            return

        if delete_from_wdk and wdk_id and conversation.site_id:
            try:
                api = get_strategy_api(conversation.site_id)
                await api.delete_strategy(wdk_id)
            except (VEuPathDBError, OSError, RuntimeError) as e:
                logger.warning(
                    "WDK strategy delete failed",
                    wdk_strategy_id=wdk_id,
                    error=str(e),
                )
        await stop_turn_before_delete(conversation_id)
        await self._repo.delete(conversation_id, cascade=cascade)
        await self._session.commit()

    async def get_ast(self, conversation_id: UUID, user_id: UUID) -> JSONObject:
        return await strategy_ops.get_ast(self._repo, conversation_id, user_id)

    async def restore(
        self, conversation_id: UUID, user_id: UUID
    ) -> ConversationResponse:
        restored = await strategy_ops.restore(self._repo, conversation_id, user_id)
        await self._session.commit()
        return restored

    async def apply_operation(
        self,
        conversation_id: UUID,
        user_id: UUID,
        *,
        site_id: str,
        op: GraphOperation,
    ) -> ConversationResponse:
        return await strategy_ops.apply_operation(
            self._repo, conversation_id, user_id, site_id=site_id, op=op
        )

    async def save_substrategy(
        self,
        conversation_id: UUID,
        user_id: UUID,
        *,
        site_id: str,
        step_id: str,
        name: str,
        description: str | None,
    ) -> SavedSubstrategyResult:
        return await strategy_ops.save_substrategy(
            self._repo,
            conversation_id,
            user_id,
            strategy_ops.SaveSubstrategyParams(
                site_id=site_id,
                step_id=step_id,
                name=name,
                description=description,
            ),
        )

    async def count_saved_strategy_consumers(
        self,
        user_id: UUID,
        site_id: str,
    ) -> dict[int, int]:
        return await strategy_ops.count_saved_strategy_consumers(
            self._repo, user_id, site_id
        )

    async def insert_saved(
        self,
        conversation_id: UUID,
        user_id: UUID,
        *,
        site_id: str,
        target_step_id: str,
        saved_wdk_strategy_id: int,
        operator: CombineOp,
    ) -> InsertSavedResult:
        return await strategy_ops.insert_saved(
            self._repo,
            conversation_id,
            user_id,
            strategy_ops.InsertSavedParams(
                site_id=site_id,
                target_step_id=target_step_id,
                saved_wdk_strategy_id=saved_wdk_strategy_id,
                operator=operator,
            ),
        )

    async def dismiss(self, conversation_id: UUID, user_id: UUID) -> None:
        await get_visible_conversation(self._repo, conversation_id, user_id)
        await self._repo.dismiss(conversation_id)
        await self._session.commit()

    async def duplicate(
        self,
        conversation_id: UUID,
        user_id: UUID,
    ) -> DuplicatedConversation:
        source = await get_visible_conversation(
            self._repo,
            conversation_id,
            user_id,
        )
        source_strategy = await self._repo.get_strategy(conversation_id)
        msg_repo = MessagesRepository(self._session)
        new_conv = await self._repo.create(
            user_id=user_id,
            site_id=source.site_id,
            assistant_id=source.assistant_id,
            name=f"Copy of {source.name}" if source.name else "Conversation (copy)",
        )
        # Carry the strategy over (topology + params). WDK step ids are dropped
        # so the copy re-syncs as its own fresh WDK strategy instead of sharing
        # the source's steps; wdk_strategy_id stays None for the same reason.
        copied_ast = dict(source_strategy.strategy_ast)
        copied_ast.pop("wdkStepIds", None)
        copied_ast.pop("wdk_step_ids", None)
        if copied_ast:
            self._session.add(
                ConversationStrategy(
                    conversation_id=new_conv.id,
                    strategy_ast=copied_ast,
                ),
            )
        for row in await msg_repo.list_messages_for_conversation(conversation_id):
            await msg_repo.insert_message(
                message_id=uuid4(),
                conversation_id=new_conv.id,
                role=row.role,
                metadata=row.metadata_,
            )
        await self._session.execute(
            text(
                """
                INSERT INTO conversation_events (
                    conversation_id, turn_id, task_id, chunk
                )
                SELECT :dst, turn_id, task_id, chunk
                FROM conversation_events
                WHERE conversation_id = :src
                ORDER BY id ASC
                """,
            ),
            {"src": str(conversation_id), "dst": str(new_conv.id)},
        )
        await self._session.commit()
        return DuplicatedConversation(id=new_conv.id, name=new_conv.name)

    async def begin(
        self,
        *,
        conversation_id: UUID,
        user_id: UUID,
        site_id: str,
        assistant_id: str,
        experiment_id: str | None,
    ) -> BegunConversation:
        result = await begin_conversation(
            session=self._session,
            conversation_id=conversation_id,
            user_id=user_id,
            site_id=site_id,
            assistant_id=assistant_id,
            experiment_id=experiment_id,
        )
        await self._session.commit()
        return BegunConversation(
            conversation_id=result.conversation.id,
            is_new=result.is_new,
            name=result.conversation.name,
        )
