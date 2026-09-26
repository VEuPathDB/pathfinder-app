"""An edit made on the site to the thread's open analysis reaches the Lead.

The analysis is bound through the service on plasmodb as the registered test
account, changed through the EDA user service directly as the site changes it,
and read by the pre-turn hook and a Lead turn on the mock model.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation, ConversationEvent
from assistant_core.platform import db
from pydantic_ai.messages import ModelRequest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda import (
    EdaAnalysesClient,
    EdaStringSetFilter,
    EdaSubsetDescriptor,
    get_eda_analyses_client,
)

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.pre_turn import pathfinder_pre_turn
from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.models.mock import get_mock_model
from pathfinder.ai.tools.standalone.eda_stream_parts import eda_analysis_state_chunk
from pathfinder.domain.eda_parts import EdaAnalysisState
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.persistence.models import User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.eda import binding
from pathfinder.services.eda.authoring import resolve_eda_user_id
from pathfinder.tests._support.published_studies import published_on

pytestmark = [pytest.mark.asyncio, pytest.mark.live_wdk]

_SITE = "plasmodb"
_DATASET = "DS_53f554ec6a"
_CHANGED = (
    f"- the open analysis ({_DATASET}) changed after the card in this conversation"
)
_BERGHEI = EdaStringSetFilter.model_validate(
    {
        "entityId": "GENE_PHENOTYPE_DATA_ENTITY",
        "variableId": "VAR_035294d0",
        "type": "stringSet",
        "stringSet": ["P. berghei"],
    }
)
# EDA stamps a document to the second, so an edit must land in a later one.
_ONE_STAMP = 1.1


@pytest.fixture
async def signed_in(require_wdk_creds: str) -> AsyncIterator[None]:
    handle = veupathdb_auth_token_ctx.set(require_wdk_creds)
    yield
    veupathdb_auth_token_ctx.reset(handle)


async def _seed_thread() -> tuple[UUID, UUID]:
    conversation_id, user_id = uuid4(), uuid4()
    async with db.async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id=_SITE,
                name="site edit",
            )
        )
        await session.commit()
    return conversation_id, user_id


async def _show(conversation_id: UUID, state: EdaAnalysisState) -> None:
    """Put the analysis card on the thread, as the tool that bound it does."""
    async with db.async_session_factory() as session:
        session.add(
            ConversationEvent(
                conversation_id=conversation_id,
                chunk=eda_analysis_state_chunk(state).model_dump(
                    by_alias=True, mode="json", exclude_none=True
                ),
            )
        )
        await session.commit()


async def _edit_on_the_site(analyses: EdaAnalysesClient, analysis_id: str) -> None:
    user_id = await resolve_eda_user_id(_SITE)
    document = await analyses.get(user_id=user_id, analysis_id=analysis_id)
    await analyses.patch_descriptor(
        user_id=user_id,
        analysis_id=analysis_id,
        descriptor=document.descriptor.model_copy(
            update={"subset": EdaSubsetDescriptor(descriptor=[_BERGHEI])}
        ),
    )


def _turn(conversation_id: UUID, user_id: UUID) -> tuple[PipelineState, Context]:
    state = PipelineState(
        conversation_id=conversation_id,
        user_id=user_id,
        site_id=_SITE,
        mode="strategy",
        user_prompt="Which of these genes are kinases? [[arc:kinase-question]]",
        user_message_id=uuid4(),
    )
    context = Context(
        site_id=_SITE,
        user_id=user_id,
        strategy_session=StrategySession(site_id=_SITE),
        db_session_factory=db.async_session_factory,
        cancel_event=asyncio.Event(),
    )
    return state, context


async def _instructions_the_lead_read(state: PipelineState, context: Context) -> str:
    deps = LeadDeps(state=state, intent=None, runtime=context, retrieved_memories=[])
    bind_scripted_scope(context.site_id, state.user_prompt)
    result = await build_lead_agent().run(
        state.user_prompt, deps=deps, model=get_mock_model()
    )
    requests = [m for m in result.all_messages() if isinstance(m, ModelRequest)]
    return requests[0].instructions or ""


async def test_an_edit_made_on_the_site_reaches_the_leads_briefing(
    signed_in: None,
    patch_app_db_engine: None,
    db_cleaner: None,
) -> None:
    del signed_in, patch_app_db_engine, db_cleaner
    conversation_id, user_id = await _seed_thread()
    async with published_on(_SITE, _DATASET, organism="Plasmodium berghei ANKA"):
        bound = await binding.bind_analysis(
            _SITE,
            dataset_id=_DATASET,
            conversation_id=conversation_id,
            display_name="site edit probe",
        )
    analyses = get_eda_analyses_client(_SITE)
    try:
        await _show(conversation_id, bound)
        state, context = _turn(conversation_id, user_id)

        quiet = await pathfinder_pre_turn(state.model_copy(deep=True), context)
        await asyncio.sleep(_ONE_STAMP)
        await _edit_on_the_site(analyses, bound.analysis_id)
        briefed = await pathfinder_pre_turn(state.model_copy(deep=True), context)
        instructions = await _instructions_the_lead_read(briefed, context)
    finally:
        await analyses.delete(
            user_id=await resolve_eda_user_id(_SITE), analysis_id=bound.analysis_id
        )

    assert _CHANGED not in quiet.domain.turn_briefing
    assert _CHANGED in briefed.domain.turn_briefing
    assert _CHANGED in instructions
    assert "- changed after the card in this conversation" in instructions
