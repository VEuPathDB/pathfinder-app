"""A stored synthesis summary keeps its references, and every read of the run renders them."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector

from pathfinder.ai.audit.facts import audit_run_fact
from pathfinder.domain.audit.verdicts import MAX_CARD, ReviewAgreement, StoredSynthesis
from pathfinder.domain.statistic_facts import (
    StatisticFact,
    StatisticRowFact,
    statistic_id,
)
from pathfinder.platform.config import get_settings
from pathfinder.services.audit.reviews import defer_review, store_synthesis
from pathfinder.services.audit.runs import RunOwner, readable_run
from pathfinder.services.audit.views import run_view
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.http.conftest import client_for
from pathfinder.tests.integration.jobs._audit_jobs import TOKEN, holding, registered
from pathfinder.tests.integration.jobs._audit_reviews import (
    finished_run,
    high,
    work_reviews,
)

pytestmark = pytest.mark.usefixtures("site_login_names_the_user")


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


async def _read_run(app: FastAPI, owner: RunOwner, run_id: UUID) -> dict[str, Any]:
    async with client_for(app, owner.user_id) as client:
        response = await client.get(f"/api/v1/audits/{run_id}")
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()
    return found


def _counts(run_id: UUID) -> str:
    return statistic_id("audit_synthesis", [str(run_id)])


async def test_the_summary_is_stored_with_its_references_and_read_rendered(
    jobs: InMemoryConnector,
) -> None:
    owner, run_id, _ = await finished_run({n: high(n) for n in (1, 2, 3)})
    await defer_review(run_id)

    await work_reviews(jobs)

    record = await readable_run(run_id, owner.user_id)
    read = audit_run_fact(await run_view(run_id, owner.user_id))
    assert record.synthesis is not None
    assert (record.synthesis.summary, read.value("synthesis.summary")) == (
        (
            f"The review kept [stat:{_counts(run_id)}.kept] findings as errors and "
            f"rejected [stat:{_counts(run_id)}.rejected]."
        ),
        "The review kept 3 findings as errors and rejected 0.",
    )


async def test_a_stored_summary_that_renders_past_the_card_still_reads(
    jobs: InMemoryConnector, app: FastAPI
) -> None:
    del jobs
    owner, run_id, _ = await finished_run({1: high(1)})
    cause = ("The relatives of the model run longer than it does. " * 9)[:437]
    fact = StatisticFact(
        id="stat_0c0ffee0",
        kind="audit_run",
        title="Audit run",
        rows=[StatisticRowFact(name="stages.halted", value=cause, form="sentence")],
    )
    cite = " [cite:stat_0c0ffee0.stages.halted]."
    summary = ("The review keeps the truncated models. " * 30)[
        : 1156 - len(cite)
    ] + cite
    await store_synthesis(
        run_id,
        StoredSynthesis(
            sections=(),
            headline=(),
            summary=summary,
            agreement=ReviewAgreement(sampled=0, agreed=0),
            facts=(fact,),
        ),
    )

    read = audit_run_fact(await run_view(run_id, owner.user_id))
    run = await _read_run(app, owner, run_id)

    shown = summary[: -len(cite)] + f" ({cause})."
    assert (len(summary), len(shown) > MAX_CARD) == (1156, True)
    assert (run["synthesis"]["summary"], read.value("synthesis.summary")) == (
        shown,
        shown,
    )
