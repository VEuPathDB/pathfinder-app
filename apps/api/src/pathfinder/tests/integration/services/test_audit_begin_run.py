"""An audit begun from a conversation: every refusal comes before a write, and a start queues one job."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from assistant_core.platform.db import async_session_factory
from procrastinate.testing import InMemoryConnector
from pydantic import ValidationError
from veupathdb.errors import WDKLoginRequiredError

from pathfinder.domain.audit.scope import AuditScope
from pathfinder.persistence.models import AuditRunRecord
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.platform.audit_errors import AuditNeedsAThreadError
from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import ErrorCode
from pathfinder.services.audit.job import begin_run
from pathfinder.services.audit.queue import AUDIT_QUEUE, audit_lock
from pathfinder.services.audit.sign_in import AuditsDisabledError
from pathfinder.services.audit.verdicts import AuditCaller
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.jobs._audit_jobs import (
    TOKEN,
    audit_jobs,
    holding,
    registered,
)

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

_GENOMES = ("Examplea alpha A", "Examplea alpha B", "Examplea beta C")
_SCOPE = AuditScope(site_id="plasmodb", genomes=_GENOMES[:1], checks=("gene_length",))


@pytest.fixture
def signed_in(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    registered(monkeypatch, TOKEN)
    with holding(TOKEN):
        yield


@pytest.fixture
def sealing(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with sealed_provider_keys(monkeypatch):
        yield


async def _runs(user_id: UUID) -> list[AuditRunRecord]:
    async with async_session_factory() as session:
        return await AuditRepository(session).runs(user_id=user_id)


@pytest.mark.usefixtures("signed_in")
async def test_a_start_with_no_secret_writes_no_run(
    in_memory_jobs: InMemoryConnector,
) -> None:
    owner = await seed_thread()

    with pytest.raises(AuditsDisabledError) as refused:
        await begin_run(owner=owner, scope=_SCOPE)

    assert refused.value.code == ErrorCode.AUDITS_DISABLED
    assert await _runs(owner.user_id) == []
    assert audit_jobs(in_memory_jobs) == []


@pytest.mark.usefixtures("sealing")
async def test_a_start_without_a_registered_sign_in_writes_no_run(
    in_memory_jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    registered(monkeypatch, TOKEN)
    owner = await seed_thread()

    with holding("a-guest-token"), pytest.raises(WDKLoginRequiredError):
        await begin_run(owner=owner, scope=_SCOPE)

    assert await _runs(owner.user_id) == []
    assert audit_jobs(in_memory_jobs) == []


@pytest.mark.usefixtures("sealing", "signed_in")
async def test_a_start_over_the_cap_writes_no_run(
    in_memory_jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    three = _over_the_cap(monkeypatch)
    owner = await seed_thread()

    with pytest.raises(ValidationError, match="at most 2 whole genomes, not 3"):
        await begin_run(owner=owner, scope=three)

    assert await _runs(owner.user_id) == []
    assert audit_jobs(in_memory_jobs) == []


def _over_the_cap(monkeypatch: pytest.MonkeyPatch) -> AuditScope:
    monkeypatch.setenv("AUDIT_MAX_GENOMES", "2")
    get_settings.cache_clear()
    return AuditScope(site_id="plasmodb", genomes=_GENOMES, checks=("gene_length",))


async def test_no_secret_is_refused_before_the_sign_in_and_the_cap(
    in_memory_jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    registered(monkeypatch, TOKEN)
    over = _over_the_cap(monkeypatch)
    owner = await seed_thread()

    with holding("a-guest-token"), pytest.raises(AuditsDisabledError):
        await begin_run(owner=owner, scope=over)

    assert await _runs(owner.user_id) == []
    assert audit_jobs(in_memory_jobs) == []


@pytest.mark.usefixtures("sealing")
async def test_an_unregistered_sign_in_is_refused_before_the_cap(
    in_memory_jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    registered(monkeypatch, TOKEN)
    over = _over_the_cap(monkeypatch)
    owner = await seed_thread()

    with holding("a-guest-token"), pytest.raises(WDKLoginRequiredError):
        await begin_run(owner=owner, scope=over)

    assert await _runs(owner.user_id) == []
    assert audit_jobs(in_memory_jobs) == []


@pytest.mark.usefixtures("sealing", "signed_in")
async def test_a_start_queues_one_job(in_memory_jobs: InMemoryConnector) -> None:
    owner = await seed_thread()

    started = await begin_run(owner=owner, scope=_SCOPE)

    (run,) = await _runs(owner.user_id)
    assert (started.run_id, started.status, started.halted) == (
        run.id,
        "planned",
        None,
    )
    assert (run.scope, run.conversation_id) == (_SCOPE, owner.conversation_id)
    (job,) = audit_jobs(in_memory_jobs)
    assert (job["task_name"], job["queue_name"], job["lock"]) == (
        "audit:run",
        AUDIT_QUEUE,
        audit_lock(run.id),
    )


def test_a_caller_with_no_thread_starts_nothing() -> None:
    caller = AuditCaller(user_id=uuid4(), conversation_id=None, site_id="plasmodb")

    with pytest.raises(AuditNeedsAThreadError) as refused:
        caller.owner()

    assert (refused.value.code, refused.value.status, refused.value.title) == (
        ErrorCode.AUDIT_NEEDS_A_THREAD,
        409,
        "An audit starts from a conversation",
    )


def test_a_caller_in_a_thread_owns_its_runs() -> None:
    user_id, conversation_id = uuid4(), uuid4()
    owner = AuditCaller(
        user_id=user_id, conversation_id=conversation_id, site_id="plasmodb"
    ).owner()

    assert (owner.user_id, owner.conversation_id) == (user_id, conversation_id)
