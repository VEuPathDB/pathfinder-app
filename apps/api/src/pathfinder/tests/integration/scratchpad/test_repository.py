from __future__ import annotations

from uuid import UUID

import pytest
from assistant_core.persistence.models import Conversation
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.scratchpad.models import NoteCreate, NoteUpdate
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories.scratchpad import ScratchpadRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID


@pytest.fixture
async def conv_id(db_session: AsyncSession, seed_user: User) -> UUID:
    """Insert a conversation; return its id."""
    conv = Conversation(
        assistant_id=PATHFINDER_ASSISTANT_ID,
        user_id=seed_user.id,
        site_id="plasmodb",
        name="",
    )
    db_session.add(conv)
    await db_session.flush()
    await db_session.commit()
    return conv.id


class TestCreateAndRead:
    async def test_create_and_get(
        self,
        db_session: AsyncSession,
        conv_id: UUID,
    ) -> None:
        repo = ScratchpadRepository(db_session)
        created = await repo.create(
            conversation_id=conv_id,
            data=NoteCreate(
                title="Leading candidate",
                summary="GenesByRNASeq with params X = 1200 genes",
                body="Full body of the note.",
                tags=["candidate"],
            ),
        )
        await db_session.commit()
        assert created.id.startswith("n-")
        fetched = await repo.get(conversation_id=conv_id, note_id=created.id)
        assert fetched is not None
        assert fetched.title == "Leading candidate"
        assert fetched.body_tokens == len("Full body of the note.") // 4


class TestUpdate:
    async def test_partial_update_body_refreshes_tokens(
        self,
        db_session: AsyncSession,
        conv_id: UUID,
    ) -> None:
        repo = ScratchpadRepository(db_session)
        created = await repo.create(
            conversation_id=conv_id,
            data=NoteCreate(title="t", summary="s", body="x" * 40),
        )
        await db_session.commit()

        updated = await repo.update(
            conversation_id=conv_id,
            note_id=created.id,
            patch=NoteUpdate(body="y" * 400),
        )
        await db_session.commit()
        assert updated.body == "y" * 400
        assert updated.body_tokens == 100

    async def test_update_missing_returns_none_sentinel_via_error(
        self,
        db_session: AsyncSession,
        conv_id: UUID,
    ) -> None:
        repo = ScratchpadRepository(db_session)
        result = await repo.get(conversation_id=conv_id, note_id="n-nope")
        assert result is None


class TestListAndSearch:
    async def test_list_for_index_pinned_first(
        self,
        db_session: AsyncSession,
        conv_id: UUID,
    ) -> None:
        repo = ScratchpadRepository(db_session)
        for i in range(3):
            await repo.create(
                conversation_id=conv_id,
                data=NoteCreate(title=f"t{i}", summary="s", body="b"),
            )
        pinned = await repo.create(
            conversation_id=conv_id,
            data=NoteCreate(title="pinned", summary="s", body="b", pinned=True),
        )
        await db_session.commit()
        notes = await repo.list_for_index(conversation_id=conv_id, recent_limit=10)
        ids = [n.id for n in notes]
        assert ids[0] == pinned.id

    async def test_list_by_tag(
        self,
        db_session: AsyncSession,
        conv_id: UUID,
    ) -> None:
        repo = ScratchpadRepository(db_session)
        await repo.create(
            conversation_id=conv_id,
            data=NoteCreate(title="a", summary="s", body="b", tags=["alpha"]),
        )
        await repo.create(
            conversation_id=conv_id,
            data=NoteCreate(title="b", summary="s", body="b", tags=["beta"]),
        )
        await db_session.commit()
        alphas = await repo.list_notes(conversation_id=conv_id, tag="alpha")
        assert {n.title for n in alphas} == {"a"}

    async def test_search_notes_fts_hit(
        self,
        db_session: AsyncSession,
        conv_id: UUID,
    ) -> None:
        repo = ScratchpadRepository(db_session)
        await repo.create(
            conversation_id=conv_id,
            data=NoteCreate(
                title="GenesByRNASeq candidate",
                summary="Stage-differential, 1200 genes",
                body="Using threshold 2, gametocyte_vs_asexual.",
            ),
        )
        await repo.create(
            conversation_id=conv_id,
            data=NoteCreate(
                title="Dead end: GenesByGO",
                summary="Lost stage specificity",
                body="Do not retry.",
            ),
        )
        await db_session.commit()
        hits = await repo.search_notes(
            conversation_id=conv_id,
            query="gametocyte threshold",
        )
        assert any("GenesByRNASeq" in n.title for n in hits)


class TestPinAndDelete:
    async def test_pin_toggle(
        self,
        db_session: AsyncSession,
        conv_id: UUID,
    ) -> None:
        repo = ScratchpadRepository(db_session)
        created = await repo.create(
            conversation_id=conv_id,
            data=NoteCreate(title="t", summary="s", body="b"),
        )
        await db_session.commit()
        pinned = await repo.set_pinned(
            conversation_id=conv_id,
            note_id=created.id,
            pinned=True,
        )
        await db_session.commit()
        assert pinned.pinned is True

    async def test_delete(
        self,
        db_session: AsyncSession,
        conv_id: UUID,
    ) -> None:
        repo = ScratchpadRepository(db_session)
        created = await repo.create(
            conversation_id=conv_id,
            data=NoteCreate(title="t", summary="s", body="b"),
        )
        await db_session.commit()
        deleted = await repo.delete(conversation_id=conv_id, note_id=created.id)
        await db_session.commit()
        assert deleted is True
        assert await repo.get(conversation_id=conv_id, note_id=created.id) is None


class TestTotalsAndReplaceNonPinned:
    async def test_totals(
        self,
        db_session: AsyncSession,
        conv_id: UUID,
    ) -> None:
        repo = ScratchpadRepository(db_session)
        for i in range(5):
            await repo.create(
                conversation_id=conv_id,
                data=NoteCreate(title=f"t{i}", summary="s", body="x" * 40),
            )
        await db_session.commit()
        count, tokens = await repo.totals(conversation_id=conv_id)
        assert count == 5
        assert tokens == 5 * 10

    async def test_compactable_totals_excludes_pinned(
        self,
        db_session: AsyncSession,
        conv_id: UUID,
    ) -> None:
        repo = ScratchpadRepository(db_session)
        # 3 pinned + 2 non-pinned. `totals` sees all 5; `compactable_totals`
        # sees only the 2 non-pinned notes.
        for i in range(3):
            await repo.create(
                conversation_id=conv_id,
                data=NoteCreate(
                    title=f"pin{i}",
                    summary="s",
                    body="x" * 40,
                    pinned=True,
                ),
            )
        for i in range(2):
            await repo.create(
                conversation_id=conv_id,
                data=NoteCreate(title=f"np{i}", summary="s", body="y" * 80),
            )
        await db_session.commit()

        total_count, total_tokens = await repo.totals(conversation_id=conv_id)
        comp_count, comp_tokens = await repo.compactable_totals(
            conversation_id=conv_id,
        )
        assert total_count == 5
        assert total_tokens == 3 * 10 + 2 * 20
        assert comp_count == 2
        assert comp_tokens == 2 * 20

    async def test_replace_non_pinned_keeps_pinned(
        self,
        db_session: AsyncSession,
        conv_id: UUID,
    ) -> None:
        repo = ScratchpadRepository(db_session)
        pinned = await repo.create(
            conversation_id=conv_id,
            data=NoteCreate(title="pin", summary="s", body="b", pinned=True),
        )
        await repo.create(
            conversation_id=conv_id,
            data=NoteCreate(title="old1", summary="s", body="b"),
        )
        await repo.create(
            conversation_id=conv_id,
            data=NoteCreate(title="old2", summary="s", body="b"),
        )
        await db_session.commit()

        await repo.replace_non_pinned(
            conversation_id=conv_id,
            new_notes=[
                NoteCreate(title="merged", summary="s", body="b"),
            ],
        )
        await db_session.commit()

        remaining = await repo.list_notes(conversation_id=conv_id, limit=100)
        titles = sorted(n.title for n in remaining)
        assert titles == ["merged", "pin"]
        assert any(n.id == pinned.id for n in remaining)
