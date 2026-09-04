"""Extraction reads finished threads of consenting users, and nothing else."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.ui_message_reducer import user_message_chunk
from assistant_core.persistence.models import Conversation, ConversationEvent
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.types import JSONObject
from pydantic_ai.ui.vercel_ai.response_types import TextDeltaChunk
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.graph.stream_events import ledger_update_event
from pathfinder.ai.lead.ledger_sections import VerificationSection
from pathfinder.evals.case import ExpectedOutcome
from pathfinder.evals.store import load_case
from pathfinder.persistence.models import ConversationStrategy, User
from pathfinder.persistence.repositories.eval_staging import EvalStagingRepository
from pathfinder.services.eval_data.consent import PrivacyUpdate, update_privacy
from pathfinder.services.eval_data.curation import (
    PromotionEdits,
    default_expectation,
    promote_staged_case,
    staged_extract,
)
from pathfinder.services.eval_data.extraction import extract_eval_candidates
from pathfinder.tests._support.ledger import ledger_with

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

_AST: JSONObject = {
    "recordType": "transcript",
    "root": {
        "id": "step_root",
        "searchName": "__combine__",
        "operator": "INTERSECT",
        "primaryInput": {"id": "step_a", "searchName": "GenesByText"},
        "secondaryInput": {"id": "step_b", "searchName": "GenesByTaxon"},
    },
}


def _user_chunk(text: str) -> JSONObject:
    return user_message_chunk(
        message_id=str(uuid4()),
        parts=[{"type": "text", "text": text}],
    )


def _reply_chunk(text: str) -> JSONObject:
    return TextDeltaChunk(id="lead-prose-1", delta=text).model_dump(
        by_alias=True,
        mode="json",
        exclude_none=True,
    )


def _ledger_chunk(*, success: bool) -> JSONObject:
    """The ledger chunk a finished turn writes, built by the code that writes it."""
    section = VerificationSection(
        digest=VerificationDigest(
            disposition=PhaseDisposition.DONE,
            prose="prose",
            reason="root size holds",
            success=success,
        ),
    )
    chunk = ledger_update_event(ledger=ledger_with(section))
    return chunk.model_dump(by_alias=True, mode="json", exclude_none=True)


async def _seed_thread(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    request: str = "find kinases",
    with_strategy: bool = True,
    with_verdict: bool = True,
    reply: str = "Built it.",
) -> UUID:
    conversation_id = uuid4()
    async with session_maker() as session:
        session.add(
            Conversation(id=conversation_id, user_id=user_id, site_id="plasmodb"),
        )
        await session.flush()
        chunks: list[JSONObject] = [
            _user_chunk(request),
            _reply_chunk(reply),
        ]
        if with_verdict:
            chunks.append(_ledger_chunk(success=True))
        for chunk in chunks:
            session.add(
                ConversationEvent(conversation_id=conversation_id, chunk=chunk),
            )
        if with_strategy:
            session.add(
                ConversationStrategy(
                    conversation_id=conversation_id,
                    record_type="transcript",
                    step_count=3,
                    strategy_ast=_AST,
                ),
            )
        await session.commit()
    return conversation_id


@pytest.fixture
async def consenting_user(
    session_maker: async_sessionmaker[AsyncSession],
) -> UUID:
    user_id = uuid4()
    async with session_maker() as session:
        session.add(User(id=user_id))
        await session.commit()
    return user_id


@pytest.fixture
def staging() -> EvalStagingRepository:
    return EvalStagingRepository(session_factory=async_session_factory)


async def test_consent_is_on_by_default(
    consenting_user: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    async with session_maker() as session:
        user = await session.get(User, consenting_user)
        assert user is not None
        assert user.eval_data_consent is True
        assert user.eval_notice_seen_at is None


async def test_a_finished_thread_is_staged(
    consenting_user: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    staging: EvalStagingRepository,
) -> None:
    await _seed_thread(session_maker, user_id=consenting_user)

    report = await extract_eval_candidates()

    assert report.staged == 1
    rows = await staging.list_staged()
    extract = staged_extract(rows[0])
    assert [t.request for t in extract.turns] == ["find kinases"]
    assert extract.strategy is not None
    assert extract.strategy.structure == "(GenesByText INTERSECT GenesByTaxon)"
    assert extract.verification is not None
    assert extract.verification.success


async def test_a_thread_with_no_verdict_is_not_staged(
    consenting_user: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_thread(session_maker, user_id=consenting_user, with_verdict=False)

    assert (await extract_eval_candidates()).staged == 0


async def test_a_thread_that_built_nothing_is_still_staged(
    consenting_user: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    staging: EvalStagingRepository,
) -> None:
    """A turn that correctly refused to build is exactly the case worth keeping."""
    await _seed_thread(session_maker, user_id=consenting_user, with_strategy=False)

    assert (await extract_eval_candidates()).staged == 1
    rows = await staging.list_staged()
    assert staged_extract(rows[0]).strategy is None


async def test_a_second_pass_stages_nothing_new(
    consenting_user: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_thread(session_maker, user_id=consenting_user)
    await extract_eval_candidates()

    assert (await extract_eval_candidates()).staged == 0


async def test_a_queued_thread_leaves_the_batch_so_the_next_one_is_reached(
    consenting_user: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A batch of one must still advance, or a full queue starves the rest."""
    await _seed_thread(session_maker, user_id=consenting_user, request="first")
    assert (await extract_eval_candidates(limit=1)).staged == 1
    await _seed_thread(session_maker, user_id=consenting_user, request="second")

    report = await extract_eval_candidates(limit=1)

    assert report.considered == 1
    assert report.staged == 1


async def test_a_thread_that_never_finishes_does_not_hold_the_batch(
    consenting_user: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    staging: EvalStagingRepository,
) -> None:
    """The batch reads newest first, so an old unfinished thread cannot block one."""
    await _seed_thread(
        session_maker,
        user_id=consenting_user,
        request="never finished",
        with_verdict=False,
    )
    await _seed_thread(session_maker, user_id=consenting_user, request="finished")

    assert (await extract_eval_candidates(limit=1)).staged == 1
    rows = await staging.list_staged()
    assert staged_extract(rows[0]).turns[0].request == "finished"


async def test_an_opted_out_user_is_never_read(
    consenting_user: UUID,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    await _seed_thread(session_maker, user_id=consenting_user)
    async with session_maker() as session:
        await update_privacy(
            session,
            consenting_user,
            PrivacyUpdate(eval_data_consent=False),
        )

    report = await extract_eval_candidates()

    assert report.considered == 0
    assert report.staged == 0


async def test_opting_out_clears_what_was_already_staged(
    consenting_user: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    staging: EvalStagingRepository,
) -> None:
    await _seed_thread(session_maker, user_id=consenting_user)
    await extract_eval_candidates()
    assert len(await staging.list_staged()) == 1

    async with session_maker() as session:
        await update_privacy(
            session,
            consenting_user,
            PrivacyUpdate(eval_data_consent=False),
        )

    assert await staging.list_staged() == []


async def test_opting_back_in_lets_the_thread_stage_again(
    consenting_user: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    staging: EvalStagingRepository,
) -> None:
    await _seed_thread(session_maker, user_id=consenting_user)
    await extract_eval_candidates()
    async with session_maker() as session:
        await update_privacy(
            session,
            consenting_user,
            PrivacyUpdate(eval_data_consent=False),
        )
    async with session_maker() as session:
        await update_privacy(
            session,
            consenting_user,
            PrivacyUpdate(eval_data_consent=True),
        )

    assert (await extract_eval_candidates()).staged == 1
    assert len(await staging.list_staged()) == 1


async def test_an_email_in_a_request_does_not_reach_the_queue(
    consenting_user: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    staging: EvalStagingRepository,
) -> None:
    await _seed_thread(
        session_maker,
        user_id=consenting_user,
        request="send results to ada@example.org",
    )

    await extract_eval_candidates()

    rows = await staging.list_staged()
    assert staged_extract(rows[0]).turns[0].request == (
        "send results to [redacted-email]"
    )


async def test_promotion_writes_a_case_and_ends_the_association(
    consenting_user: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    staging: EvalStagingRepository,
    tmp_path: Path,
) -> None:
    await _seed_thread(session_maker, user_id=consenting_user)
    await extract_eval_candidates()
    row = (await staging.list_staged())[0]
    staging_id = row.id

    path = await promote_staged_case(
        staging=staging,
        staging_id=staging_id,
        edits=PromotionEdits(
            name="a-promoted-case",
            rationale="pins the intersect build",
            expected=ExpectedOutcome(builds_strategy=True, step_count=3),
        ),
        directory=tmp_path,
    )

    assert path.is_file()
    case = load_case("a-promoted-case", directory=tmp_path)
    assert case.provenance.origin == "promoted"
    assert case.provenance.staging_id == str(staging_id)
    assert case.site_id == "plasmodb"
    promoted = await staging.get(staging_id)
    assert promoted is not None
    assert promoted.user_id is None
    assert promoted.source_conversation_id is None


async def test_a_promoted_case_survives_the_user(
    consenting_user: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    staging: EvalStagingRepository,
    tmp_path: Path,
) -> None:
    await _seed_thread(session_maker, user_id=consenting_user)
    await extract_eval_candidates()
    staging_id = (await staging.list_staged())[0].id
    await promote_staged_case(
        staging=staging,
        staging_id=staging_id,
        edits=PromotionEdits(name="a-surviving-case", rationale="pins a build"),
        directory=tmp_path,
    )

    async with session_maker() as session:
        user = await session.get(User, consenting_user)
        assert user is not None
        await session.delete(user)
        await session.commit()

    assert await staging.get(staging_id) is not None
    assert load_case("a-surviving-case", directory=tmp_path).name == "a-surviving-case"


async def test_the_default_expectation_repeats_the_recorded_run(
    consenting_user: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    staging: EvalStagingRepository,
) -> None:
    await _seed_thread(session_maker, user_id=consenting_user)
    await extract_eval_candidates()
    extract = staged_extract((await staging.list_staged())[0])

    expectation = default_expectation(extract)

    assert expectation.builds_strategy
    assert expectation.structure == "(GenesByText INTERSECT GenesByTaxon)"
    assert expectation.step_count == 3
    assert expectation.verified is True
