from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from veupathdb.errors import WDKError

from pathfinder.domain.strategy.constraints import ConstraintKind, ConstraintSource
from pathfinder.tests._support.explore_turns import (
    EXPLORE_PROMPT,
    FIRST_READING,
    GENE_TYPE_REPORT,
    NO_READING_PROMPT,
    SECOND_READING,
    SIGNAL_PEPTIDE_REPORT,
    serve_recorded_readings,
)
from pathfinder.tests._support.recorded_counts import recorded_count
from pathfinder.tests._support.recorded_searches import (
    serve_recorded_plasmodb,
    suite_search,
)
from pathfinder.tests.integration.chat._helpers import (
    answer_card,
    approval_tool_names,
    checkpointed,
    dispatched,
    post_chat_turn,
    routes,
    run_one_chat_turn,
    turn_modes,
    types,
)
from pathfinder.tests.integration.http._lead_audit_turns import domain_of
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import install_stub_api

BUILD_ARC_TOKEN = "[[arc:echo]]"
TYPED_PROMPT = f"the second one {BUILD_ARC_TOKEN}"

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "signed_in_to_veupathdb", "app_memory_store"
)


@pytest.fixture(autouse=True)
def recorded_plasmodb(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded_readings(monkeypatch)
    serve_recorded_plasmodb(
        monkeypatch,
        [
            suite_search("search_genes_with_signal_peptide"),
            suite_search("search_genes_by_gene_type"),
        ],
    )
    install_stub_api(monkeypatch).refuse = WDKError("Service Unavailable", 503)


async def test_the_pick_is_a_requirement(
    app: FastAPI, authed_user_id: UUID, in_memory_jobs: InMemoryConnector
) -> None:
    cid = uuid4()
    asked = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=EXPLORE_PROMPT,
        conversation_id=cid,
        mode="explore",
    )
    chunks = await post_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        body=answer_card(cid, asked, [SECOND_READING], mode="explore"),
    )
    domain = await domain_of(cid)
    assert [(c.kind, c.requested_value, c.source) for c in domain.requirements] == [
        (ConstraintKind.UNTYPED, SECOND_READING, ConstraintSource.USER_EXPLICIT)
    ]
    assert domain.picked_readings == [SECOND_READING]
    assert domain.offered_readings[SECOND_READING].spec.criteria[0].search_name == (
        "GenesByGeneType"
    )
    assert "frame" in dispatched(chunks)
    assert (await turn_modes(cid))[-1] == ("assistant", "build")


async def test_the_pick_does_not_set_the_request_aside(
    app: FastAPI, authed_user_id: UUID, in_memory_jobs: InMemoryConnector
) -> None:
    cid = uuid4()
    asked = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=EXPLORE_PROMPT,
        conversation_id=cid,
    )
    await post_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        body=answer_card(cid, asked, [FIRST_READING], mode="auto"),
    )
    domain = await domain_of(cid)
    assert EXPLORE_PROMPT in domain.request_messages
    assert domain.reading_labels() == [FIRST_READING, SECOND_READING]


async def test_a_typed_reply_over_the_readings_card_keeps_the_offer_in_the_exchanges(
    app: FastAPI, authed_user_id: UUID, in_memory_jobs: InMemoryConnector
) -> None:
    cid = uuid4()
    await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=EXPLORE_PROMPT,
        conversation_id=cid,
    )
    await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=f"the second one {BUILD_ARC_TOKEN}",
        conversation_id=cid,
    )
    domain = await domain_of(cid)
    assert domain.exchanges[0].card == (
        f"Readings offered: {FIRST_READING} ({recorded_count(SIGNAL_PEPTIDE_REPORT)} genes); "
        f"{SECOND_READING} ({recorded_count(GENE_TYPE_REPORT)} genes)"
    )


async def _readings_card(
    app: FastAPI, user_id: UUID, connector: InMemoryConnector, cid: UUID
) -> None:
    asked = await run_one_chat_turn(
        app=app,
        user_id=user_id,
        connector=connector,
        prompt=EXPLORE_PROMPT,
        conversation_id=cid,
        mode="explore",
    )
    assert approval_tool_names(asked) == ["consult_user"]


async def test_a_typed_message_over_the_readings_card_in_explore_mode_goes_to_explore(
    app: FastAPI, authed_user_id: UUID, in_memory_jobs: InMemoryConnector
) -> None:
    cid = uuid4()
    await _readings_card(app, authed_user_id, in_memory_jobs, cid)
    chunks = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=TYPED_PROMPT,
        conversation_id=cid,
        mode="explore",
    )
    assert (routes(chunks), approval_tool_names(chunks)) == (["explore"], [])
    assert (await turn_modes(cid))[-1] == ("assistant", "explore")
    assert [(await checkpointed(cid)).pending_approval] == [None]


async def test_a_typed_message_over_the_readings_card_in_build_mode_is_a_new_message(
    app: FastAPI, authed_user_id: UUID, in_memory_jobs: InMemoryConnector
) -> None:
    cid = uuid4()
    await _readings_card(app, authed_user_id, in_memory_jobs, cid)
    chunks = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=TYPED_PROMPT,
        conversation_id=cid,
        mode="build",
    )
    domain = await domain_of(cid)
    assert routes(chunks) == ["build"]
    assert [(await checkpointed(cid)).pending_approval] == [None]
    assert [(e.kind, e.said) for e in domain.exchanges[1:]] == [
        ("message", TYPED_PROMPT)
    ]
    assert [c.requested_value for c in domain.requirements] == []


async def test_a_reply_with_no_buildable_reading_offers_no_card(
    app: FastAPI, authed_user_id: UUID, in_memory_jobs: InMemoryConnector
) -> None:
    chunks = await run_one_chat_turn(
        app=app,
        user_id=authed_user_id,
        connector=in_memory_jobs,
        prompt=NO_READING_PROMPT,
        mode="explore",
    )
    assert "tool-approval-request" not in types(chunks)
    assert "text-delta" in types(chunks)
