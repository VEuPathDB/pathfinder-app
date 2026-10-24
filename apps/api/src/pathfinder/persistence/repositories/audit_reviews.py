"""The verdicts a model wrote about gene models, and the review state and synthesis of a run."""

from __future__ import annotations

from uuid import UUID

from assistant_core.platform.context import calling_application
from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.audit.verdicts import (
    FindingReview,
    GeneModelVerdict,
    ReviewProgress,
    StoredSynthesis,
    VerdictOrigin,
)
from pathfinder.persistence.models import (
    AuditFinding,
    AuditRun,
    AuditVerdict,
    AuditVerdictRecord,
)
from pathfinder.persistence.rows import rows_changed

_PENDING = ("waiting", "reviewing")


class AuditReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _add(self, row: AuditVerdict) -> int:
        self.session.add(row)
        await self.session.flush()
        return row.id

    async def add_verdict(
        self,
        *,
        user_id: UUID,
        conversation_id: UUID | None,
        site_id: str,
        origin: VerdictOrigin,
        verdict: GeneModelVerdict,
        model_id: str,
    ) -> int:
        return await self._add(
            AuditVerdict(
                user_id=user_id,
                conversation_id=conversation_id,
                site_id=site_id,
                origin=origin,
                verdict=verdict.model_dump(by_alias=True, mode="json"),
                model_id=model_id,
            )
        )

    async def add_review(
        self, *, run_id: UUID, finding_id: int, review: FindingReview, model_id: str
    ) -> int:
        owner = (
            await self.session.execute(
                select(
                    AuditRun.user_id,
                    AuditRun.application_id,
                    AuditRun.conversation_id,
                    AuditRun.site_id,
                ).where(AuditRun.id == run_id)
            )
        ).one()
        return await self._add(
            AuditVerdict(
                user_id=owner.user_id,
                application_id=owner.application_id,
                conversation_id=owner.conversation_id,
                run_id=run_id,
                finding_id=finding_id,
                site_id=owner.site_id,
                origin="review",
                verdict=review.verdict.model_dump(by_alias=True, mode="json"),
                review=review.model_dump(
                    by_alias=True, mode="json", exclude={"verdict"}
                ),
                model_id=model_id,
            )
        )

    async def of_run(self, run_id: UUID) -> list[AuditVerdictRecord]:
        found = await self.session.scalars(
            select(AuditVerdict)
            .where(AuditVerdict.run_id == run_id)
            .order_by(AuditVerdict.id)
        )
        return [AuditVerdictRecord.model_validate(row) for row in found]

    async def of_conversation(
        self, conversation_id: UUID, user_id: UUID
    ) -> list[AuditVerdictRecord]:
        found = await self.session.scalars(
            select(AuditVerdict)
            .where(
                AuditVerdict.conversation_id == conversation_id,
                AuditVerdict.user_id == user_id,
                AuditVerdict.application_id == calling_application(),
            )
            .order_by(AuditVerdict.created_at.desc(), AuditVerdict.id.desc())
        )
        return [AuditVerdictRecord.model_validate(row) for row in found]

    async def unreviewed(self, run_id: UUID, limit: int) -> list[int]:
        reviewed = exists().where(AuditVerdict.finding_id == AuditFinding.id)
        found = await self.session.scalars(
            select(AuditFinding.id)
            .where(
                AuditFinding.run_id == run_id,
                AuditFinding.status == "confirmed",
                AuditFinding.error_type.is_not(None),
                ~reviewed,
            )
            .order_by(AuditFinding.impact.desc().nulls_last(), AuditFinding.id)
            .limit(limit)
        )
        return list(found)

    async def reviewed_count(self, run_id: UUID) -> int:
        counted = await self.session.execute(
            select(func.count())
            .select_from(AuditVerdict)
            .where(AuditVerdict.run_id == run_id, AuditVerdict.origin == "review")
        )
        return counted.scalar_one()

    async def set_review(self, run_id: UUID, progress: ReviewProgress) -> None:
        await self.session.execute(
            update(AuditRun)
            .where(AuditRun.id == run_id)
            .values(review=progress.model_dump(by_alias=True, mode="json"))
        )

    async def set_synthesis(self, run_id: UUID, synthesis: StoredSynthesis) -> None:
        await self.session.execute(
            update(AuditRun)
            .where(AuditRun.id == run_id)
            .values(synthesis=synthesis.model_dump(by_alias=True, mode="json"))
        )

    async def reopen_review(self, run_id: UUID) -> None:
        waiting = ReviewProgress(status="waiting")
        await self.session.execute(
            update(AuditRun)
            .where(AuditRun.id == run_id)
            .values(
                review=waiting.model_dump(by_alias=True, mode="json"), synthesis=None
            )
        )

    async def pending_reviews(self) -> list[UUID]:
        found = await self.session.scalars(
            select(AuditRun.id)
            .where(
                AuditRun.status == "finished",
                AuditRun.stages["halted"].astext.is_(None),
                AuditRun.review["status"].astext.in_(_PENDING),
            )
            .order_by(AuditRun.finished_at, AuditRun.id)
        )
        return list(found)

    async def delete_for_user(self, *, user_id: UUID, site_id: str | None) -> int:
        if site_id == "":
            msg = "a purge names a site, or None for every site"
            raise ValueError(msg)
        statement = delete(AuditVerdict).where(
            AuditVerdict.user_id == user_id,
            AuditVerdict.application_id == calling_application(),
        )
        if site_id is not None:
            statement = statement.where(AuditVerdict.site_id == site_id)
        return rows_changed(await self.session.execute(statement))
