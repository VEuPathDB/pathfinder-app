"""A thread, its strategy row and its gene sets, held in memory for naming tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from assistant_core.persistence.models import Conversation
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.persistence.repositories.conversation_strategy import (
    ConversationWithStrategy,
)
from pathfinder.persistence.repositories.conversation_update import (
    ConversationUpdate,
)
from pathfinder.platform.errors import NotFoundError
from pathfinder.services.gene_sets.types import GeneSet

WDK_ID = 330679883


def ast_named(name: str | None) -> dict[str, Any]:
    return StrategyAst(
        record_type="transcript",
        name=name,
        root=StrategyStepNode(id="step_a", search_name="GenesByTaxon"),
    ).model_dump(by_alias=True, exclude_none=True, mode="json")


@dataclass
class Threads:
    """One thread and its strategy row, written the way the repository writes."""

    conversation: Conversation
    strategy: ConversationStrategyView
    suffix: str = ""
    """What the store appends to keep a name unique."""

    async def get_with_strategy(
        self, conversation_id: UUID, /
    ) -> ConversationWithStrategy | None:
        if conversation_id != self.conversation.id:
            return None
        return self.conversation, self.strategy

    async def get_strategy(self, conversation_id: UUID, /) -> ConversationStrategyView:
        del conversation_id
        return self.strategy

    async def update_conversation(
        self, conversation_id: UUID, upd: ConversationUpdate, /
    ) -> None:
        del conversation_id
        if upd.name is not None:
            upd.name = f"{upd.name}{self.suffix}"
            self.conversation.name = upd.name
        if upd.strategy_ast is not None:
            self.strategy = self.strategy.model_copy(
                update={
                    "strategy_ast": upd.strategy_ast.model_dump(
                        by_alias=True, exclude_none=True, mode="json"
                    )
                }
            )
        if upd.wdk_strategy_id_set:
            self.strategy = self.strategy.model_copy(
                update={"wdk_strategy_id": upd.wdk_strategy_id}
            )

    @property
    def ast_name(self) -> str | None:
        return StrategyAst.model_validate(self.strategy.strategy_ast).name


def thread_row(
    *,
    name: str = "",
    ast_name: str | None = "New Conversation",
    gene_set_id: str | None = None,
) -> Threads:
    now = datetime.now(UTC)
    conversation = Conversation(
        id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        name=name,
        created_at=now,
        updated_at=now,
    )
    strategy = ConversationStrategyView(
        wdk_strategy_id=WDK_ID,
        strategy_ast=ast_named(ast_name),
        gene_set_id=gene_set_id,
        gene_set_auto_imported=gene_set_id is not None,
    )
    return Threads(conversation=conversation, strategy=strategy)


@dataclass
class Sets:
    held: dict[str, GeneSet] = field(default_factory=dict)

    async def get_for_user(self, user_id: UUID, gene_set_id: str) -> GeneSet:
        del user_id
        found = self.held.get(gene_set_id)
        if found is None:
            raise NotFoundError(detail=gene_set_id)
        return found

    async def rename(self, gene_set: GeneSet, name: str) -> None:
        gene_set.name = name


def gene_set(name: str, owner: UUID) -> GeneSet:
    return GeneSet(
        id="gs-1",
        name=name,
        site_id="plasmodb",
        gene_ids=["PF3D7_0100100"],
        source="strategy",
        user_id=owner,
    )
