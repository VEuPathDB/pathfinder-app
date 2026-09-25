"""A gene id list the step editor sends reaches the PlasmoDB step it edits.

The editor sends a dataset parameter as the JSON of a dataset source
(``{"sourceType": "idList", "sourceContent": {"ids": [...]}}``) inside an
``input-dataset`` value. The step on the site answers exactly those ids.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.parameters import InputDatasetValue
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.wdk import (
    WDKDatasetConfigIdList,
    WDKDatasetIdListContent,
    get_results_api,
    get_strategy_api,
)

from pathfinder.domain.strategy.operations import UpdateStepParamsOp
from pathfinder.persistence.models import PersistedStrategyGraph, User
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.conversations.strategy_ops import apply_operation
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.session_factory import build_strategy_session
from pathfinder.services.strategies.spec_build import build_strategy_from_spec

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_SITE = "plasmodb"
_PARAM = "ds_gene_ids"
_FIRST = ["PF3D7_1133400"]
_EDITED = ["PF3D7_1133400", "PF3D7_0709000", "PF3D7_0100100"]


@dataclass
class _Built:
    user_id: UUID
    conv_id: UUID
    wdk_step_id: int


@pytest.fixture
async def built(
    require_wdk_creds: str,
    patch_app_db_engine: None,
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[_Built]:
    """A one-step id-list strategy PathFinder built on PlasmoDB."""
    del patch_app_db_engine, db_cleaner
    reset = veupathdb_auth_token_ctx.set(require_wdk_creds)
    api = get_strategy_api(_SITE)
    dataset_id = await api.create_dataset(
        WDKDatasetConfigIdList(
            source_type="idList",
            source_content=WDKDatasetIdListContent(ids=list(_FIRST)),
        )
    )
    user_id, conv_id = uuid4(), uuid4()
    async with session_maker() as session:
        session.add(User(id=user_id))
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conv_id,
                user_id=user_id,
                site_id=_SITE,
                name="ids",
            )
        )
        await session.commit()
    outcome = await build_strategy_from_spec(
        deps=StrategyMutationContext(
            site_id=_SITE,
            strategy_session=build_strategy_session(
                site_id=_SITE,
                strategy_graph=PersistedStrategyGraph(
                    id=str(conv_id),
                    name="ids",
                    strategy_ast=None,
                    wdk_strategy_id=None,
                ),
            ),
            conversation_id=conv_id,
            db_session_factory=async_session_factory,
        ),
        root=StrategyStepNode(
            id="leaf",
            search_name="GeneByLocusTag",
            parameters={_PARAM: InputDatasetValue(dataset_id=str(dataset_id))},
        ),
    )
    assert outcome.failed_steps == [], outcome.failed_steps
    assert outcome.wdk_strategy_id is not None
    try:
        held = await api.get_strategy(outcome.wdk_strategy_id)
        yield _Built(user_id=user_id, conv_id=conv_id, wdk_step_id=held.root_step_id)
    finally:
        with contextlib.suppress(Exception):
            await api.delete_strategy(outcome.wdk_strategy_id)
        veupathdb_auth_token_ctx.reset(reset)


async def test_a_pasted_id_list_is_the_list_the_step_answers(
    built: _Built, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    pasted = json.dumps({"sourceType": "idList", "sourceContent": {"ids": _EDITED}})
    async with session_maker() as session:
        await apply_operation(
            ConversationRepository(session),
            built.conv_id,
            built.user_id,
            site_id=_SITE,
            op=UpdateStepParamsOp.model_validate(
                {
                    "kind": "updateStepParams",
                    "stepId": "leaf",
                    "parameters": {
                        _PARAM: {"type": "input-dataset", "datasetId": pasted}
                    },
                }
            ),
        )

    answer = await get_results_api(_SITE).get_step_preview(built.wdk_step_id, limit=50)
    assert sorted(r.display_name for r in answer.records) == sorted(_EDITED)
