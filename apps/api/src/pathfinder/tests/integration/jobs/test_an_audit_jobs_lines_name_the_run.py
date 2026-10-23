from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest
from assistant_core.platform.db import async_session_factory
from procrastinate.testing import InMemoryConnector
from pydantic import ValidationError
from sqlalchemy import update

from pathfinder.persistence.models import AuditRun
from pathfinder.platform.config import get_settings
from pathfinder.services.audit import checks
from pathfinder.services.audit.job import start_run
from pathfinder.services.audit.runs import create_run, owned_run
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests._support.rendered_logs import rendered_logs
from pathfinder.tests.integration.jobs._audit_jobs import (
    SCOPE,
    TOKEN,
    audit_jobs,
    holding,
    registered,
    wire_checks,
    work_through,
)

_KEYS = ("run_id", "user_id", "conversation_id", "site_id")


@pytest.fixture
def jobs(
    db_cleaner: None,
    patch_app_db_engine: None,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[InMemoryConnector]:
    del db_cleaner, patch_app_db_engine
    registered(monkeypatch, TOKEN)
    with sealed_provider_keys(monkeypatch), holding(TOKEN):
        yield in_memory_jobs
    get_settings.cache_clear()


async def test_a_line_an_audit_job_writes_names_the_run_and_its_owner(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    fakes = wire_checks(monkeypatch)

    async def length(site_id: str, gene: str) -> object:
        logging.getLogger("veupathdb_mcp.audit").warning("check line")
        return await fakes.length(site_id, gene)

    monkeypatch.setattr(checks, "audit_gene_length", length)
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)

    with rendered_logs() as logs:
        await work_through(jobs)
        logging.getLogger("veupathdb_mcp.audit").warning("after the run")

    named = {
        tuple(line[key] for key in _KEYS)
        for line in logs.lines()
        if line["event"] == "check line"
    }
    assert named == {
        (str(run_id), str(owner.user_id), str(owner.conversation_id), "plasmodb")
    }
    assert set(_KEYS) & set(logs.line("after the run")) == set()


async def test_a_run_whose_site_is_not_an_id_is_marked_failed(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    wire_checks(monkeypatch)
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await start_run(run_id, owner)
    async with async_session_factory() as session:
        await session.execute(
            update(AuditRun).where(AuditRun.id == run_id).values(site_id="a@b.org")
        )
        await session.commit()
    assert len(audit_jobs(jobs)) == 1

    with pytest.raises(ValidationError):
        await work_through(jobs)

    halted = await owned_run(run_id, owner)
    assert str(halted.stages.halted).split(": ")[:2] == [
        "the audit job failed",
        "ValidationError",
    ]
