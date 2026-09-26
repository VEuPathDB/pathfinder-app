"""A separation run parks the Lead, its result reopens the turn on the adoption
card, and the researcher's answer builds the measured spec or keeps the offer.

The whole PathFinder assistant over the real chat route, the real turn graph,
the real checkpointer, the real worker runner and the real database. The model
is the deterministic Lead; the tool server's run is its recorded plasmodb
answer, and the push to the site is recorded instead of sent.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.persistence.models import ConversationEvent
from assistant_core.platform.db import async_session_factory
from assistant_core.tasks.runner import run_durable_task
from fastapi import FastAPI
from langchain_core.runnables import RunnableConfig
from procrastinate.testing import InMemoryConnector
from sqlalchemy import select
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb_mcp.separation import (
    SeparationProgress,
    SeparationRequest,
    SeparationResult,
)

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import sub_agent_dispatch
from pathfinder.ai.lead.proposal import DeclinedProposal
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.domain.separation import SeparationOffer
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.jobs.impls import register_all_tools
from pathfinder.persistence.models import ControlSet
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.evidence import separation
from pathfinder.services.experiment.seed.catalog import get_seeds_for_site
from pathfinder.services.strategies.sync_state import ensure_sync_state
from pathfinder.tests._support.separation import SIGNAL_PEPTIDE, recorded_separation
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
    chat_turn_jobs,
    parse_sse_body,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)
from pathfinder.tests.integration.http.conftest import client_for

_SEED = next(
    seed
    for seed in get_seeds_for_site("plasmodb")
    if seed.name == "PF3D7 Signal Peptide Genes"
).control_set
_PROMPT = (
    "Find a strategy that separates these controls, exact. [[arc:separation]]\n"
    f"Positive controls: {' '.join(_SEED.positive_ids)}\n"
    f"Negative controls: {' '.join(_SEED.negative_ids)}"
)
_RUN = "separate_controls"
_ADOPT = "adopt_separating_strategy"
_TIMEOUT_SECONDS = 120.0
_WDK_STEP = 440589000

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "signed_in_to_veupathdb", "worker_seams"
)


@pytest.fixture
def pushed(monkeypatch: pytest.MonkeyPatch) -> list[StrategyStepNode]:
    """The tool server's recorded run, and the roots a build would push."""
    roots: list[StrategyStepNode] = []

    async def _recorded(
        site_id: str,
        request: SeparationRequest,
        *,
        strategy_name: str,
        progress: SeparationProgress,
    ) -> SeparationResult:
        del site_id, request, strategy_name, progress
        return recorded_separation(SIGNAL_PEPTIDE)

    async def _push(**kwargs: Any) -> BuildOutcome:
        root: StrategyStepNode = kwargs["root"]
        session: StrategySession = kwargs["deps"].strategy_session
        graph = session.get_graph(None)
        assert graph is not None
        graph.steps = flatten_tree(root)
        graph.recompute_roots()
        ensure_sync_state(session).wdk_step_ids = {
            step_id: _WDK_STEP + index for index, step_id in enumerate(graph.steps)
        }
        roots.append(root)
        return BuildOutcome(pushed_step_ids=list(graph.steps))

    monkeypatch.setattr(separation, "separate", _recorded)
    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _push)
    return roots


async def _turn(
    app: FastAPI, user_id: UUID, jobs: InMemoryConnector, body: dict[str, Any]
) -> list[dict[str, Any]]:
    queued = len(chat_turn_jobs(jobs))
    async with client_for(app, user_id) as client:
        post = asyncio.create_task(
            client.post("/api/v1/chat", json=body, timeout=_TIMEOUT_SECONDS),
        )
        await asyncio.wait_for(
            wait_until_chat_turn_deferred(jobs, queued), timeout=_TIMEOUT_SECONDS
        )
        await run_deferred_chat_turns()
        response = await asyncio.wait_for(post, timeout=_TIMEOUT_SECONDS)
    assert response.status_code == 200, response.text
    return parse_sse_body(response.text)


def _answer(
    conversation_id: UUID, tool: str, call_id: str, *, approved: bool
) -> dict[str, Any]:
    """The body the client sends when the researcher answers a card."""
    message_id = str(uuid4())
    return {
        "trigger": "submit-message",
        "id": message_id,
        "messages": [
            {
                "id": message_id,
                "role": "assistant",
                "parts": [
                    {
                        "type": f"tool-{tool}",
                        "toolCallId": call_id,
                        "state": "approval-responded",
                        "input": {},
                        "approval": {"id": call_id, "approved": approved},
                    },
                ],
            },
        ],
        "conversationId": str(conversation_id),
        "siteId": "plasmodb",
    }


async def _rows(conversation_id: UUID) -> list[dict[str, Any]]:
    async with async_session_factory() as session:
        found = await session.scalars(
            select(ConversationEvent)
            .where(ConversationEvent.conversation_id == conversation_id)
            .order_by(ConversationEvent.id),
        )
        return [row.chunk for row in found]


def _asked(chunks: list[dict[str, Any]], tool: str) -> str:
    offered = {
        c["toolCallId"]
        for c in chunks
        if c["type"] == "tool-input-available" and c["toolName"] == tool
    }
    (call_id,) = [
        c["toolCallId"]
        for c in chunks
        if c["type"] == "tool-approval-request" and c["toolCallId"] in offered
    ]
    return str(call_id)


async def _domain(conversation_id: UUID) -> StrategyDomainState:
    spec = get_assistant_registry().resolve(PATHFINDER_ASSISTANT_ID)
    config: RunnableConfig = {"configurable": {"thread_id": str(conversation_id)}}
    async with lifespan_checkpointer(get_settings().database_url) as saver:
        snapshot = await spec.build_graph(saver).aget_state(config)
    return StrategyDomainState.model_validate(snapshot.values["domain"])


def _the_offer(domain: StrategyDomainState) -> SeparationOffer:
    """The one offer the thread holds."""
    (offer,) = domain.separation_offers.values()
    return offer


async def _offered(
    app: FastAPI, user_id: UUID, jobs: InMemoryConnector, conversation_id: UUID
) -> str:
    """Ask, approve the run, work its job; answer the adoption card's call id."""
    asked = await _turn(app, user_id, jobs, chat_post_body(conversation_id, _PROMPT))
    await _turn(
        app,
        user_id,
        jobs,
        _answer(conversation_id, _RUN, _asked(asked, _RUN), approved=True),
    )
    (job,) = [j for j in jobs.jobs.values() if j["task_name"] == f"durable:{_RUN}"]
    register_all_tools()
    payload = job["args"]
    await run_durable_task(
        tool_name=_RUN,
        task_id=str(payload["task_id"]),
        thread_id=str(payload["thread_id"]),
        args=payload["args"],
        job_context=payload["job_context"],
    )
    return _asked(await _rows(conversation_id), _ADOPT)


async def test_the_result_reopens_the_turn_on_the_adoption_card(
    app: FastAPI,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    pushed: list[StrategyStepNode],
) -> None:
    conversation_id = uuid4()

    await _offered(app, authed_user_id, in_memory_jobs, conversation_id)

    rows = await _rows(conversation_id)
    (report,) = [c["data"] for c in rows if c["type"] == "data-separation-result"]
    domain = await _domain(conversation_id)
    assert list(domain.separation_offers) == [report["taskId"]]
    assert domain.separation_offers[report["taskId"]].question == (
        "Build the closest strategy found: 3 searches returning 61 of 80 "
        "positives and 2 of 40 negatives in 1,132 genes?"
    )
    assert pushed == []


async def test_a_yes_builds_the_measured_spec_and_attaches_its_controls(
    app: FastAPI,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    pushed: list[StrategyStepNode],
) -> None:
    conversation_id = uuid4()
    call_id = await _offered(app, authed_user_id, in_memory_jobs, conversation_id)

    await _turn(
        app,
        authed_user_id,
        in_memory_jobs,
        _answer(conversation_id, _ADOPT, call_id, approved=True),
    )

    domain = await _domain(conversation_id)
    offer = _the_offer(domain)
    assert [c for c in await _rows(conversation_id) if c["type"] == "error"] == []
    leaves = [s for s in flatten_tree(pushed[0]).values() if not s.input_ids()]
    assert [(s.search_name, s.parameters) for s in leaves] == [
        (c.search_name, c.resolved_params) for c in offer.spec.criteria
    ]
    async with async_session_factory() as session:
        saved = list(await session.scalars(select(ControlSet)))
    assert [(s.source, len(s.positive_ids), len(s.negative_ids)) for s in saved] == [
        ("separation", 80, 40)
    ]
    attached = domain.attached_controls
    assert attached is not None
    assert attached.control_set_id == str(saved[0].id)
    (tested,) = [
        job["args"]["args"]["kwargs"]
        for job in in_memory_jobs.jobs.values()
        if job["task_name"] == "durable:run_control_tests_on_step"
    ]
    assert (tested["positive_controls"], tested["negative_controls"]) == (
        attached.positives,
        attached.negatives,
    )


async def test_a_no_keeps_the_offer_and_builds_nothing(
    app: FastAPI,
    authed_user_id: UUID,
    in_memory_jobs: InMemoryConnector,
    pushed: list[StrategyStepNode],
) -> None:
    conversation_id = uuid4()
    call_id = await _offered(app, authed_user_id, in_memory_jobs, conversation_id)

    chunks = await _turn(
        app,
        authed_user_id,
        in_memory_jobs,
        _answer(conversation_id, _ADOPT, call_id, approved=False),
    )

    domain = await _domain(conversation_id)
    assert [c["toolCallId"] for c in chunks if c["type"] == "tool-output-denied"] == [
        call_id
    ]
    assert [c for c in chunks if c["type"] == "text-delta"] == []
    assert pushed == []
    assert len(domain.separation_offers) == 1
    offer = _the_offer(domain)
    assert domain.declined_proposal == DeclinedProposal(
        question=offer.question,
        proposed_changes=[
            f"{criterion.text} ({criterion.role})" for criterion in offer.spec.criteria
        ],
        note="",
    )
