"""Creation of one owned instance of every resource kind the matrix covers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.store import MemoryStore
from assistant_core.persistence.models import Conversation, Message
from assistant_core.persistence.repositories.scratchpad import ScratchpadRepository
from assistant_core.scratchpad.models import NoteCreate
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.parameters import SinglePickValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from pathfinder.persistence.models import ControlSet, ConversationStrategy
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.experiment.store import get_experiment_store
from pathfinder.services.experiment.types import Experiment, ExperimentConfig
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.store import get_gene_set_store
from pathfinder.tests.integration.http._authz_matrix_support import (
    GENE_IDS,
    MEMORY_KIND,
    ROOT_STEP_ID,
    SITE_ID,
    Owned,
)
from pathfinder.tests.integration.http.conftest import make_user


def placeholder_owned() -> Owned:
    """Ids that address nothing, for the checks that never issue a request."""
    return Owned(
        user_id=uuid4(),
        conversation_id=uuid4(),
        unclaimed_conversation_id=uuid4(),
        note_id="note-1",
        message_id=uuid4(),
        experiment_ids=(str(uuid4()), str(uuid4())),
        gene_set_ids=(str(uuid4()), str(uuid4())),
        control_set_id=uuid4(),
        memory_key=str(uuid4()),
    )


def _strategy_ast() -> dict[str, Any]:
    root = StrategyStepNode(
        id=ROOT_STEP_ID,
        search_name="GenesByTaxon",
        display_name="Taxon",
        parameters={"organism": SinglePickValue(value="Plasmodium falciparum 3D7")},
    )
    ast = StrategyAst(record_type="transcript", root=root)
    return ast.model_dump(by_alias=True, exclude_none=True, mode="json")


def _experiment(user_id: UUID) -> Experiment:
    return Experiment(
        id=str(uuid4()),
        user_id=str(user_id),
        config=ExperimentConfig(
            site_id=SITE_ID,
            record_type="transcript",
            search_name="GenesByText",
            parameters={},
            positive_controls=[GENE_IDS[0]],
            negative_controls=[GENE_IDS[1]],
            controls_search_name="GeneByLocusTag",
            controls_param_name="ds_gene_ids",
            name="owner experiment",
        ),
        created_at=datetime.now(UTC).isoformat(),
    )


async def _create_rows(
    session: AsyncSession,
) -> tuple[Conversation, Message, str, UUID]:
    """Insert the database-backed resources and return what addresses them."""
    owner = await make_user(session)
    conversation = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        user_id=owner.id,
        site_id=SITE_ID,
        name="Owner kinases",
    )
    session.add(conversation)
    await session.flush()
    session.add(
        ConversationStrategy(
            conversation_id=conversation.id,
            strategy_ast=_strategy_ast(),
        ),
    )
    await session.flush()
    message = Message(
        id=uuid4(),
        conversation_id=conversation.id,
        role="user",
        metadata_={},
    )
    session.add(message)
    note = await ScratchpadRepository(session).create(
        conversation_id=conversation.id,
        data=NoteCreate(title="t", summary="s", body="b"),
    )
    control_set = ControlSet(
        id=uuid4(),
        name="owner controls",
        site_id=SITE_ID,
        record_type="transcript",
        positive_ids=[GENE_IDS[0]],
        negative_ids=[],
        tags=[],
        user_id=owner.id,
        is_public=False,
    )
    session.add(control_set)
    await session.flush()
    await session.commit()
    return conversation, message, note.id, control_set.id


async def create_owned(session: AsyncSession, store: MemoryStore) -> Owned:
    """Create a fresh user holding one instance of every owned resource kind."""
    conversation, message, note_id, control_set_id = await _create_rows(session)
    owner_id = conversation.user_id

    experiments = [_experiment(owner_id) for _ in range(2)]
    for experiment in experiments:
        get_experiment_store().save(experiment)
    gene_sets = [
        await GeneSetService(get_gene_set_store()).create(
            user_id=owner_id,
            name=f"owner set {index}",
            site_id=SITE_ID,
            gene_ids=list(GENE_IDS),
            source="paste",
        )
        for index in range(2)
    ]
    memory_key = await store.put(
        user_id=owner_id,
        value=MemoryValue(
            kind=MEMORY_KIND,
            name="owner memory",
            summary="kinases of interest",
            content={},
            created_at=datetime.now(UTC),
        ),
    )
    return Owned(
        user_id=owner_id,
        conversation_id=conversation.id,
        unclaimed_conversation_id=uuid4(),
        note_id=note_id,
        message_id=message.id,
        experiment_ids=(experiments[0].id, experiments[1].id),
        gene_set_ids=(gene_sets[0].id, gene_sets[1].id),
        control_set_id=control_set_id,
        memory_key=memory_key,
    )
