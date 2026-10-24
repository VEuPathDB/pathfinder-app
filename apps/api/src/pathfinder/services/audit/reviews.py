"""The review job of a finished audit run: queueing it, the findings it reviews, and what it stores."""

from __future__ import annotations

from uuid import UUID

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel, computed
from assistant_core.tasks.app import task_app
from procrastinate.exceptions import AlreadyEnqueued
from pydantic import BaseModel, ConfigDict

from pathfinder.domain.audit.sampling import sampled
from pathfinder.domain.audit.stages import RunStatus
from pathfinder.domain.audit.verdicts import (
    AGREEMENT_SAMPLE,
    MAX_REVIEWS_PER_RUN,
    FindingReview,
    ReviewProgress,
    ReviewStatus,
    StoredSynthesis,
)
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
)
from pathfinder.persistence.repositories.audit_reviews import AuditReviewRepository
from pathfinder.services.audit.finding_views import FindingDetail, finding_detail
from pathfinder.services.audit.queue import (
    AUDIT_QUEUE,
    AUDIT_REVIEW_JOB,
    audit_lock,
    working,
)
from pathfinder.services.audit.runs import RunOwner, owned_run
from pathfinder.services.audit.verdicts import VerdictView

logger = get_logger(__name__)

_NAMED = FindingFilter(statuses=("confirmed",), named=True)


class ReviewJob(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: UUID


class ReviewedRun(CamelModel):
    model_config = ConfigDict(frozen=True)

    run_id: UUID
    user_id: UUID
    conversation_id: UUID | None
    site_id: str
    status: RunStatus
    seed: int
    review: ReviewProgress | None
    named: int

    @computed
    def total(self) -> int:
        return min(self.named, MAX_REVIEWS_PER_RUN)


async def reviewed_run(run_id: UUID) -> ReviewedRun | None:
    async with async_session_factory() as session:
        run = await AuditRepository(session).stored_run(run_id)
        if run is None:
            return None
        named = await AuditFindingRepository(session).count_findings(run_id, _NAMED)
    return ReviewedRun(
        run_id=run.id,
        user_id=run.user_id,
        conversation_id=run.conversation_id,
        site_id=run.site_id,
        status=run.status,
        seed=run.seed,
        review=run.review,
        named=named,
    )


async def set_progress(run_id: UUID, progress: ReviewProgress) -> None:
    async with async_session_factory() as session:
        await AuditReviewRepository(session).set_review(run_id, progress)
        await session.commit()


async def continue_review(run_id: UUID) -> None:
    lock = audit_lock(run_id)
    deferrer = task_app().configure_task(
        name=AUDIT_REVIEW_JOB, queue=AUDIT_QUEUE, lock=lock, queueing_lock=lock
    )
    try:
        await deferrer.defer_async(
            payload=ReviewJob(run_id=run_id).model_dump(mode="json")
        )
    except AlreadyEnqueued:
        return


async def record_progress(
    run: ReviewedRun, status: ReviewStatus, message: str = ""
) -> None:
    done = await reviewed_count(run.run_id)
    await set_progress(
        run.run_id,
        ReviewProgress(status=status, done=done, total=run.total, message=message),
    )


async def queue_review(run_id: UUID) -> None:
    try:
        await continue_review(run_id)
    except Exception:
        logger.exception(
            "The review of a finished run was not queued; the resume pass queues it"
        )


async def defer_review(run_id: UUID) -> None:
    async with async_session_factory() as session:
        await AuditReviewRepository(session).reopen_review(run_id)
        await session.commit()
    await continue_review(run_id)


async def reviewed_count(run_id: UUID) -> int:
    async with async_session_factory() as session:
        return await AuditReviewRepository(session).reviewed_count(run_id)


async def _unreviewed(run_id: UUID) -> int | None:
    async with async_session_factory() as session:
        repo = AuditReviewRepository(session)
        if await repo.reviewed_count(run_id) >= MAX_REVIEWS_PER_RUN:
            return None
        found = await repo.unreviewed(run_id, 1)
    return found[0] if found else None


async def next_unreviewed(run_id: UUID, user_id: UUID) -> FindingDetail | None:
    finding_id = await _unreviewed(run_id)
    if finding_id is None:
        return None
    return await finding_detail(run_id, finding_id, user_id)


async def agreement_sample(run: ReviewedRun) -> frozenset[int]:
    async with async_session_factory() as session:
        repo = AuditReviewRepository(session)
        reviewed = await repo.of_run(run.run_id)
        paired = sum(
            verdict.review is not None and verdict.review.second_verdict is not None
            for verdict in reviewed
        )
        left = await repo.unreviewed(
            run.run_id, max(MAX_REVIEWS_PER_RUN - len(reviewed), 0)
        )
    if paired >= AGREEMENT_SAMPLE or not left:
        return frozenset()
    keys = (str(finding_id) for finding_id in left)
    picked = sampled(keys, AGREEMENT_SAMPLE - paired, run.seed)
    return frozenset(int(key) for key in picked)


async def store_review(
    run: ReviewedRun, finding_id: int, review: FindingReview, model_id: str
) -> None:
    async with async_session_factory() as session:
        await AuditReviewRepository(session).add_review(
            run_id=run.run_id, finding_id=finding_id, review=review, model_id=model_id
        )
        await session.commit()


async def stored_reviews(run_id: UUID) -> list[VerdictView]:
    async with async_session_factory() as session:
        found = await AuditReviewRepository(session).of_run(run_id)
    return [VerdictView.model_validate(record) for record in found]


async def stored_impacts(run_id: UUID) -> dict[int, float | None]:
    async with async_session_factory() as session:
        found = await AuditFindingRepository(session).findings(run_id, _NAMED)
    return {finding.id: finding.impact for finding in found}


async def store_synthesis(run_id: UUID, synthesis: StoredSynthesis) -> None:
    async with async_session_factory() as session:
        await AuditReviewRepository(session).set_synthesis(run_id, synthesis)
        await session.commit()


async def start_review(run_id: UUID, owner: RunOwner) -> ReviewProgress | None:
    run = await owned_run(run_id, owner)
    stored = run.review
    if run.status != "finished" or await working(run_id):
        return stored
    synthesized = stored is not None and stored.status == "synthesized"
    if synthesized and await _unreviewed(run_id) is None:
        return stored
    await defer_review(run_id)
    return ReviewProgress(status="waiting")


async def resume_stranded_reviews() -> None:
    async with async_session_factory() as session:
        pending = await AuditReviewRepository(session).pending_reviews()
    for run_id in pending:
        if not await working(run_id):
            await continue_review(run_id)
