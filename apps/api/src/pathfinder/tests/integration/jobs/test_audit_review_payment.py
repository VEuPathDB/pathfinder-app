"""Who pays for each reviewer run, and what a key refused between two slices of a review leaves on the run."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import pytest
from assistant_core.mcp.declaration import ToolSourceDeclarations
from assistant_core.mcp.resolution import ResolvedToolSources
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.types import PaidBy
from assistant_core.quota import get_period_totals
from procrastinate.testing import InMemoryConnector
from pydantic import SecretStr
from pydantic_ai.models import Model

from pathfinder.ai.audit import review
from pathfinder.ai.audit.review import review_model
from pathfinder.ai.capabilities.screened_sources import screened_sources
from pathfinder.domain.audit.verdicts import ReviewProgress
from pathfinder.domain.provider_keys import KeyRefusal
from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import refused_key_error
from pathfinder.services.audit import units
from pathfinder.services.audit.reviews import defer_review, reviewed_run
from pathfinder.services.provider_keys import record_refusals, store_key
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.jobs._audit_reviews import (
    finished_run,
    high,
    queued_reviews,
    spent_tokens,
    work_review,
    work_reviews,
)

_KEY = "sk-proj-sentinel-0123456789WXYZ"


@pytest.fixture
def jobs(
    db_cleaner: None,
    patch_app_db_engine: None,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[InMemoryConnector]:
    del db_cleaner, patch_app_db_engine
    with sealed_provider_keys(monkeypatch):
        yield in_memory_jobs
    get_settings.cache_clear()


async def _paid(user_id: UUID, payer: PaidBy) -> int:
    async with async_session_factory() as session:
        return (await get_period_totals(session, user_id, paid_by=payer)).tokens


async def _keyed(user_id: UUID) -> None:
    async with async_session_factory() as session:
        await store_key(session, user_id, "openai", SecretStr(_KEY))
        await session.commit()


async def test_a_review_on_the_owners_key_is_charged_to_the_owner(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    tokens = spent_tokens(monkeypatch)
    owner, run_id, _ = await finished_run({1: high(1)})
    await _keyed(owner.user_id)
    await defer_review(run_id)

    await work_reviews(jobs)

    assert len(tokens) == 3
    assert sum(tokens) > 0
    assert (
        await _paid(owner.user_id, PaidBy.USER),
        await _paid(owner.user_id, PaidBy.DEPLOYMENT),
    ) == (sum(tokens), 0)


async def test_a_review_with_no_key_of_the_owner_is_charged_to_the_deployment(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    tokens = spent_tokens(monkeypatch)
    owner, run_id, _ = await finished_run({1: high(1)})
    await defer_review(run_id)

    await work_reviews(jobs)

    assert sum(tokens) > 0
    assert (
        await _paid(owner.user_id, PaidBy.USER),
        await _paid(owner.user_id, PaidBy.DEPLOYMENT),
    ) == (0, sum(tokens))


async def test_a_key_refused_between_slices_stops_with_the_true_counts(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(units, "SLICE_SECONDS", 0.0)
    owner, run_id, _ = await finished_run({1: high(1), 2: high(2), 3: high(3)})
    await defer_review(run_id)
    (first,) = queued_reviews(jobs)
    await work_review(jobs, first)
    await _keyed(owner.user_id)
    await record_refusals(owner.user_id, {"openai": KeyRefusal.INVALID})

    await work_reviews(jobs)

    run = await reviewed_run(run_id)
    assert run is not None
    assert run.review == ReviewProgress(
        status="stopped",
        done=1,
        total=3,
        message=refused_key_error("OpenAI", KeyRefusal.INVALID).title,
    )


async def test_a_key_refused_at_the_start_opens_no_source_and_builds_no_model(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[ToolSourceDeclarations] = []
    built: list[str] = []

    def sources(declarations: ToolSourceDeclarations) -> ResolvedToolSources:
        opened.append(declarations)
        return screened_sources(declarations)

    def model(model_id: str) -> Model:
        built.append(model_id)
        return review_model(model_id)

    monkeypatch.setattr(review, "screened_sources", sources)
    monkeypatch.setattr(review, "review_model", model)
    owner, run_id, _ = await finished_run({1: high(1)})
    await _keyed(owner.user_id)
    await record_refusals(owner.user_id, {"openai": KeyRefusal.INVALID})
    await defer_review(run_id)

    await work_reviews(jobs)

    assert (opened, built) == ([], [])
    run = await reviewed_run(run_id)
    assert run is not None
    assert run.review is not None
    assert run.review.status == "stopped"
