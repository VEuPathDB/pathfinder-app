from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from assistant_core import quota
from assistant_core.models.scripted import retry_prompt_parts, terminal_call
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.types import PaidBy
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse, RetryPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import update

from pathfinder.ai.audit import review
from pathfinder.ai.audit.mock import MOCK_SYNTHESIS_MODEL_ID, build_synthesis_mock
from pathfinder.ai.audit.synthesis import NO_FINDING_KEPT
from pathfinder.domain.audit.verdicts import (
    FindingReview,
    GeneModelVerdict,
    ReviewProgress,
    VerdictKind,
    finding_cite,
)
from pathfinder.domain.statistic_facts import statistic_id
from pathfinder.persistence.models import User
from pathfinder.platform.config import get_settings
from pathfinder.services.audit.reviews import (
    defer_review,
    reviewed_run,
    start_review,
    store_review,
)
from pathfinder.services.audit.runs import RunOwner, owned_run
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.http.conftest import client_for
from pathfinder.tests.integration.jobs._audit_jobs import TOKEN, holding, registered
from pathfinder.tests.integration.jobs._audit_reviews import (
    GENOME,
    add_named,
    finished_run,
    gene,
    high,
    recorded_reviewer,
    spent_tokens,
    weighed,
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


def _review(
    finding_id: int, number: int, verdict: VerdictKind, second: VerdictKind
) -> FindingReview:
    named = verdict == "error"
    return FindingReview(
        verdict=GeneModelVerdict(
            genes=(gene(number),),
            model_genome=GENOME,
            verdict=verdict,
            error_type="truncated_model" if named else None,
            certainty="high" if named else None,
            cause=f"The relatives of {gene(number)} are longer.",
            cites=(finding_cite(finding_id),),
        ),
        already_known="not_searched",
        card_text=f"The model of {gene(number)} is short.",
        second_verdict=second,
    )


async def _stored(
    run_id: UUID, stored: dict[str, int], verdicts: dict[int, tuple[VerdictKind, ...]]
) -> None:
    run = await reviewed_run(run_id)
    assert run is not None
    for number, (verdict, second) in verdicts.items():
        finding_id = stored[gene(number)]
        await store_review(
            run, finding_id, _review(finding_id, number, verdict, second), "test:r"
        )


def _counts(run_id: UUID) -> str:
    return statistic_id("audit_synthesis", [str(run_id)])


async def _paid(owner: RunOwner) -> int:
    async with async_session_factory() as session:
        totals = await quota.get_period_totals(
            session, owner.user_id, paid_by=PaidBy.DEPLOYMENT
        )
    return totals.tokens


async def _spend_the_budget(owner: RunOwner) -> None:
    async with async_session_factory() as session:
        await session.execute(
            update(User)
            .where(User.id == owner.user_id)
            .values(monthly_cost_limit_usd=1.0)
        )
        await quota.accumulate(
            session,
            user_id=owner.user_id,
            tokens=10,
            cost_usd=Decimal("1.0"),
            paid_by=PaidBy.DEPLOYMENT,
        )
        await session.commit()


def _refusing(called: list[int]) -> FunctionModel:
    def refuse(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        called.append(1)
        return ModelResponse(parts=[terminal_call({})])

    return FunctionModel(refuse)


async def test_the_job_ends_with_the_runs_synthesis_stored(
    jobs: InMemoryConnector, app: FastAPI
) -> None:
    owner, run_id, stored = await finished_run(
        {
            1: weighed(gene(1), "low", cited=True, reference=True),
            2: high(2),
            3: weighed(gene(3), "low", cited=False, reference=False),
        }
    )
    await defer_review(run_id)

    await work_reviews(jobs)

    ids = [stored[gene(n)] for n in (2, 1, 3)]
    run = await _read_run(app, owner, run_id)
    assert run["review"] == {
        "status": "synthesized",
        "done": 3,
        "total": 3,
        "message": "",
    }
    assert run["synthesis"] == {
        "sections": [
            {
                "errorType": "truncated_model",
                "cause": f"The stored checks of {gene(2)} confirm the finding.",
                "confirmedBy": (
                    f"The stored evidence of findings {ids[0]}, {ids[1]}, {ids[2]} "
                    "confirms it."
                ),
                "findingIds": ids,
            }
        ],
        "headline": ids,
        "summary": "The review kept 3 findings as errors and rejected 0.",
        "agreement": {"sampled": 3, "agreed": 3, "share": 1.0},
    }


async def test_the_synthesis_carries_the_review_agreement(
    jobs: InMemoryConnector, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, run_id, stored = await finished_run({n: high(n) for n in (1, 2, 3)})
    await _stored(
        run_id,
        stored,
        {1: ("error", "error"), 2: ("error", "error"), 3: ("error", "no_error")},
    )
    retries: list[RetryPromptPart] = []
    ids = list(stored.values())
    kept = "The review kept 3 findings as errors and rejected 0."
    counts = _counts(run_id)
    written = (
        f"The review kept [stat:{counts}.kept] findings as errors and rejected "
        f"[stat:{counts}.rejected]."
    )

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        retries.extend(retry_prompt_parts(messages))
        summary = written if retries else "80% of the findings were kept"
        section = {
            "errorType": "truncated_model",
            "cause": "The models stop early.",
            "confirmedBy": "The relatives' lengths confirm it.",
            "findingIds": ids,
        }
        draft = {"sections": [section], "headline": ids, "summary": summary}
        return ModelResponse(parts=[terminal_call(draft)])

    monkeypatch.setattr(
        review, "synthesis_model", lambda model_id: FunctionModel(answer)
    )
    await defer_review(run_id)

    await work_reviews(jobs)

    (retry,) = retries
    assert "80" in str(retry.content)
    run = await _read_run(app, owner, run_id)
    assert run["synthesis"]["agreement"] == {"sampled": 3, "agreed": 2, "share": 0.667}
    assert (run["synthesis"]["summary"], run["synthesis"]["headline"]) == (kept, ids)
    assert run["review"]["status"] == "synthesized"


async def test_a_run_with_no_kept_finding_is_synthesized_without_a_model(
    jobs: InMemoryConnector, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, run_id, stored = await finished_run({1: high(1), 2: high(2)})
    await _stored(
        run_id, stored, {1: ("no_error", "no_error"), 2: ("undecided", "error")}
    )
    called: list[int] = []
    monkeypatch.setattr(review, "synthesis_model", lambda model_id: _refusing(called))
    await defer_review(run_id)

    await work_reviews(jobs)

    run = await _read_run(app, owner, run_id)
    assert called == []
    assert run["synthesis"] == {
        "sections": [],
        "headline": [],
        "summary": NO_FINDING_KEPT,
        "agreement": {"sampled": 2, "agreed": 1, "share": 0.5},
    }
    assert run["review"] == {
        "status": "synthesized",
        "done": 2,
        "total": 2,
        "message": "",
    }


async def test_a_synthesis_whose_retries_are_spent_stops_the_review(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    tokens = spent_tokens(monkeypatch)
    owner, run_id, _ = await finished_run({1: high(1)})
    called: list[int] = []
    monkeypatch.setattr(review, "synthesis_model", lambda model_id: _refusing(called))
    await defer_review(run_id)

    await work_reviews(jobs)

    run = await owned_run(run_id, owner)
    assert (len(called), run.synthesis) == (4, None)
    assert (len(tokens), tokens[-1] > 0) == (3, True)
    assert await _paid(owner) == sum(tokens)
    assert run.review == ReviewProgress(
        status="stopped", done=1, total=1, message=review.SYNTHESIS_STOPPED
    )
    assert review.SYNTHESIS_STOPPED == (
        "The synthesis stopped before it wrote a valid synthesis of the reviews."
    )


async def test_a_used_budget_stops_before_the_synthesis(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, run_id, stored = await finished_run({1: high(1)})
    await _stored(run_id, stored, {1: ("error", "error")})
    await _spend_the_budget(owner)
    called: list[int] = []
    monkeypatch.setattr(review, "synthesis_model", lambda model_id: _refusing(called))
    await defer_review(run_id)

    await work_reviews(jobs)

    run = await owned_run(run_id, owner)
    assert (called, run.synthesis) == ([], None)
    assert run.review == ReviewProgress(
        status="stopped", done=1, total=1, message=review.BUDGET_USED
    )


def test_the_mock_deployment_synthesizes_on_the_synthesis_script() -> None:
    model = review.synthesis_model("openai:gpt-5.6-luna")

    assert model.model_name == MOCK_SYNTHESIS_MODEL_ID


async def test_a_used_budget_with_nothing_kept_still_synthesizes(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, run_id, stored = await finished_run({1: high(1)})
    await _stored(run_id, stored, {1: ("no_error", "no_error")})
    await _spend_the_budget(owner)
    called: list[int] = []
    monkeypatch.setattr(review, "synthesis_model", lambda model_id: _refusing(called))
    await defer_review(run_id)

    await work_reviews(jobs)

    run = await owned_run(run_id, owner)
    assert called == []
    assert run.synthesis is not None
    assert run.synthesis.summary == NO_FINDING_KEPT
    assert run.review == ReviewProgress(status="synthesized", done=1, total=1)


async def test_a_provider_error_after_paid_requests_is_charged_once(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    tokens = spent_tokens(monkeypatch)
    owner, run_id, stored = await finished_run({1: high(1)})
    await _stored(run_id, stored, {1: ("error", "error")})
    asked: list[int] = []

    def fail_second(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        asked.append(1)
        if len(asked) == 2:
            raise ModelHTTPError(status_code=503, model_name="test:synthesis")
        return ModelResponse(parts=[terminal_call({})])

    monkeypatch.setattr(
        review, "synthesis_model", lambda model_id: FunctionModel(fail_second)
    )
    await defer_review(run_id)

    with pytest.raises(ModelHTTPError):
        await work_reviews(jobs)

    (spent,) = tokens
    assert (len(asked), spent > 0) == (2, True)
    assert await _paid(owner) == spent
    run = await owned_run(run_id, owner)
    assert run.synthesis is None


async def test_a_stopped_synthesis_clears_the_runs_earlier_synthesis(
    jobs: InMemoryConnector, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, run_id, _ = await finished_run({1: high(1)})
    await defer_review(run_id)
    await work_reviews(jobs)
    assert (await owned_run(run_id, owner)).synthesis is not None

    await add_named(run_id, {2: high(2)})
    assert await start_review(run_id, owner) == ReviewProgress(status="waiting")
    waiting = await _read_run(app, owner, run_id)
    assert (waiting["synthesis"], waiting["headline"]) == (None, [])
    assert waiting["agreement"]["sampled"] == 1

    called: list[int] = []
    monkeypatch.setattr(review, "synthesis_model", lambda model_id: _refusing(called))
    await work_reviews(jobs)

    run = await _read_run(app, owner, run_id)
    assert (run["synthesis"], run["headline"], len(called)) == (None, [], 4)
    assert run["review"]["status"] == "stopped"
    assert run["agreement"] == {
        "sampled": 2,
        "agreed": 2,
        "share": 1.0,
        "text": "Two independent reviews agreed on 2 of 2 sampled findings (100%)",
    }


async def test_a_later_start_reruns_only_the_stopped_synthesis(
    jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner, run_id, stored = await finished_run({1: high(1)})
    called: list[int] = []
    monkeypatch.setattr(review, "synthesis_model", lambda model_id: _refusing(called))
    await defer_review(run_id)
    await work_reviews(jobs)
    stopped = await owned_run(run_id, owner)
    assert stopped.review is not None
    assert stopped.review.message == review.SYNTHESIS_STOPPED
    recorder = recorded_reviewer(monkeypatch)
    monkeypatch.setattr(
        review, "synthesis_model", lambda model_id: build_synthesis_mock()
    )

    assert await start_review(run_id, owner) == ReviewProgress(status="waiting")
    await work_reviews(jobs)

    run = await owned_run(run_id, owner)
    assert recorder.runs() == []
    assert run.synthesis is not None
    assert run.synthesis.headline == (stored[gene(1)],)
    assert run.review == ReviewProgress(status="synthesized", done=1, total=1)
