"""Every experiment save is in the database when it returns."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.persistence.models import ExperimentRow, User
from pathfinder.services.experiment.store import ExperimentStore
from pathfinder.services.experiment.types.experiment import (
    Experiment,
    ExperimentConfig,
)

_RUN = "exp_0123456789ab"


@pytest.fixture
async def seed_user(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
    patch_app_db_engine: None,
) -> User:
    del db_cleaner, patch_app_db_engine
    user = User(id=uuid4())
    async with session_maker() as session:
        session.add(user)
        await session.commit()
    return user


def _experiment(user: User) -> Experiment:
    return Experiment(
        id=_RUN,
        config=ExperimentConfig(
            site_id="plasmodb",
            record_type="transcript",
            search_name="GenesByRNASeq",
            parameters={},
            positive_controls=["PF3D7_1133400"],
            negative_controls=["PF3D7_0709000"],
            controls_search_name="GenesByGeneList",
            controls_param_name="ds_gene_ids",
            name="RNA-Seq controls",
        ),
        user_id=str(user.id),
        status="running",
        created_at="2026-09-29T09:00:00+00:00",
    )


async def test_the_last_save_of_either_store_is_the_row(
    seed_user: User, session_maker: async_sessionmaker[AsyncSession]
) -> None:
    """The api and the worker hold two stores; the row is the last save."""
    running = _experiment(seed_user)
    await ExperimentStore().save(running)
    completed = running.model_copy(update={"status": "completed"})
    await ExperimentStore().save(completed)

    async with session_maker() as session:
        row = await session.get(ExperimentRow, _RUN)

    assert row is not None
    assert (row.status, row.name, row.site_id, row.user_id) == (
        "completed",
        "RNA-Seq controls",
        "plasmodb",
        seed_user.id,
    )
    assert Experiment.model_validate(row.data).status == "completed"
