"""A publication survives a reload.

The VDI id points at an artifact PathFinder does not own. Losing the pointer
would leave the researcher with a dataset on the site that PathFinder can no
longer name, and a second publish would make a duplicate.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.wdk import (
    VdiDatasetPostMeta,
    VdiDatasetPostResponse,
    VdiVisibility,
)

from pathfinder.persistence.models import User
from pathfinder.services.gene_sets import vdi
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.store import GeneSetStore
from pathfinder.services.gene_sets.types import GeneSet

VDI_ID = "soV5JEQEcF00p"


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


@pytest.fixture
async def seed_user(db_session: AsyncSession) -> User:
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    return user


class _FakeVdi:
    def __init__(self) -> None:
        self.sent: list[VdiDatasetPostMeta] = []

    async def create_genelist(
        self, *, details: VdiDatasetPostMeta, gene_ids: list[str]
    ) -> VdiDatasetPostResponse:
        del gene_ids
        self.sent.append(details)
        return VdiDatasetPostResponse(dataset_id=VDI_ID)


def _set(user_id: UUID, set_id: str) -> GeneSet:
    return GeneSet(
        id=set_id,
        name="Kinases",
        site_id="plasmodb",
        gene_ids=["PF3D7_1133400", "PF3D7_0709000"],
        source="paste",
        user_id=user_id,
    )


async def test_the_published_identifier_is_in_the_database_after_a_reload(
    patch_app_db_engine: None,
    seed_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine
    store = GeneSetStore()
    service = GeneSetService(store)
    gene_set = _set(seed_user.id, "gs-vdi-1")
    store.save(gene_set)
    await service.flush(gene_set.id)
    monkeypatch.setattr(vdi, "get_vdi_client", lambda site_id: _FakeVdi())

    published = await vdi.publish_to_vdi(
        service,
        seed_user.id,
        "gs-vdi-1",
        name="Kinases",
        visibility=VdiVisibility.PRIVATE,
    )

    reloaded = await GeneSetStore().aget("gs-vdi-1")
    assert published.vdi_id == VDI_ID
    assert reloaded is not None
    assert reloaded.vdi_id == VDI_ID


async def test_a_set_nobody_published_reloads_with_no_pointer(
    patch_app_db_engine: None,
    seed_user: User,
) -> None:
    del patch_app_db_engine
    store = GeneSetStore()
    service = GeneSetService(store)
    gene_set = _set(seed_user.id, "gs-vdi-2")
    store.save(gene_set)
    await service.flush(gene_set.id)

    reloaded = await GeneSetStore().aget("gs-vdi-2")

    assert reloaded is not None
    assert (reloaded.id, reloaded.name, reloaded.vdi_id) == (
        "gs-vdi-2",
        "Kinases",
        None,
    )
