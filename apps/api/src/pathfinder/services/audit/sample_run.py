"""A finished sample audit run, stored for a person on a mock deployment; its library results are recorded values."""

from __future__ import annotations

from collections.abc import Sequence
from importlib.resources import files
from importlib.resources.abc import Traversable
from typing import Literal, Self
from uuid import UUID, uuid4

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb_mcp.audit import GeneRow, GenomePriority

from pathfinder.domain.audit.findings import (
    Certainty,
    ErrorType,
    EvidenceKind,
    EvidencePayload,
)
from pathfinder.domain.audit.rates import Weighing
from pathfinder.domain.audit.scope import AuditScope, GeneTarget, GenomeRole
from pathfinder.domain.audit.stages import StageName
from pathfinder.domain.audit.verdicts import (
    FindingReview,
    ReviewProgress,
    StoredSynthesis,
    finding_cite,
)
from pathfinder.persistence.repositories.audit import AuditRepository, CollectedGenome
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    NewFinding,
    SettledFinding,
)
from pathfinder.persistence.repositories.audit_reviews import AuditReviewRepository
from pathfinder.persistence.repositories.audit_weighings import (
    AuditWeighingRepository,
)
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.audit.runs import RunOwner, add_run
from pathfinder.services.conversations.begin import begin_conversation

SAMPLE_PATH: Traversable = files("pathfinder") / "data" / "audit" / "sample_run.json"
SAMPLE_MODEL_ID = "sample"


class SampleGenome(CamelModel):
    model_config = ConfigDict(frozen=True)

    organism: str
    role: GenomeRole
    reference_strain: bool | None = None
    priority: GenomePriority | None = None
    rows: tuple[GeneRow, ...] = ()


class SampleEvidence(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: EvidenceKind
    status: Literal["stored", "unreached", "unread"]
    payload: EvidencePayload | None = None
    message: str | None = None
    requests: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _payload_or_message(self) -> Self:
        stored = self.status == "stored"
        if (self.payload is not None, self.message is None) != (stored, stored):
            msg = "sample evidence holds a payload when stored and a message otherwise"
            raise ValueError(msg)
        return self


class SampleFinding(CamelModel):
    model_config = ConfigDict(frozen=True)

    genome: str
    target: GeneTarget
    sampled: bool
    status: Literal["confirmed", "unreached", "unread", "unsampled"]
    paired_genome: str | None = None
    error_type: ErrorType | None = None
    certainty: Certainty | None = None
    message: str | None = None
    requests: int = Field(default=0, ge=0)
    weighing: Weighing | None = None
    evidence: tuple[SampleEvidence, ...] = ()

    def new(self) -> NewFinding:
        return NewFinding(
            genome=self.genome,
            target=self.target,
            sampled=self.sampled,
            status="screened" if self.status == "confirmed" else self.status,
            message=self.message,
            paired_genome=self.paired_genome,
        )

    def settled(self) -> SettledFinding:
        return SettledFinding(
            status="confirmed",
            error_type=self.error_type,
            certainty=self.certainty,
            requests=self.requests,
        )


class SampleStage(CamelModel):
    model_config = ConfigDict(frozen=True)

    name: StageName
    requests: int = Field(ge=0)
    store_reads: int = Field(ge=0)
    done: int = Field(ge=0)
    total: int = Field(ge=0)


class SampleReview(CamelModel):
    model_config = ConfigDict(frozen=True)

    place: int = Field(ge=1)
    review: FindingReview


class SampleRun(CamelModel):
    model_config = ConfigDict(frozen=True)

    scope: AuditScope
    release: str
    genomes: tuple[SampleGenome, ...]
    findings: tuple[SampleFinding, ...]
    stages: tuple[SampleStage, ...]
    reviews: tuple[SampleReview, ...]
    synthesis: StoredSynthesis
    review_progress: ReviewProgress


class SampleRunIds(CamelModel):
    model_config = ConfigDict(frozen=True)

    run_id: UUID
    finding_ids: list[int]


async def _store_genomes(
    repo: AuditRepository, run_id: UUID, genomes: Sequence[SampleGenome]
) -> None:
    await repo.add_genomes(run_id, [(g.organism, g.role) for g in genomes])
    for genome in genomes:
        await repo.try_genome(run_id, genome.organism)
        await repo.save_genome(
            run_id,
            CollectedGenome(
                organism=genome.organism,
                status="collected",
                genes=list(genome.rows),
                priority=genome.priority,
                reference_strain=genome.reference_strain,
            ),
        )


async def _store_evidence(
    repo: AuditFindingRepository, finding_id: int, evidence: SampleEvidence
) -> None:
    match evidence:
        case SampleEvidence(status="unread", message=str() as message):
            await repo.unread_evidence([finding_id], evidence.kind, message)
        case SampleEvidence(status="unreached", message=str() as message):
            await repo.try_evidence(finding_id, evidence.kind)
            await repo.fail_evidence(
                finding_id,
                evidence.kind,
                status="unreached",
                message=message,
                requests=evidence.requests,
            )
        case SampleEvidence(payload=payload) if payload is not None:
            await repo.try_evidence(finding_id, evidence.kind)
            await repo.save_evidence(finding_id, payload, requests=evidence.requests)


async def _store_findings(
    session: AsyncSession, run_id: UUID, findings: Sequence[SampleFinding]
) -> list[int]:
    repo = AuditFindingRepository(session)
    await repo.add_findings(run_id, [finding.new() for finding in findings])
    ids = [record.id for record in await repo.findings(run_id, FindingFilter())]
    for finding_id, finding in zip(ids, findings, strict=True):
        if finding.status == "confirmed":
            await repo.try_finding(finding_id)
            await repo.settle_finding(finding_id, finding.settled())
        for evidence in finding.evidence:
            await _store_evidence(repo, finding_id, evidence)
        if finding.weighing is not None:
            await AuditWeighingRepository(session).set_impact(
                finding_id, finding.weighing
            )
    return ids


async def _store_stages(repo: AuditRepository, run_id: UUID, sample: SampleRun) -> None:
    for stage in sample.stages:
        await repo.count_requests(run_id, stage.name, stage.requests, stage.store_reads)
        await repo.record_progress(
            run_id, stage.name, done=stage.done, total=stage.total, message=""
        )
        await repo.finish_stage(run_id, stage.name)
    await repo.set_release(run_id, sample.release)
    await repo.set_status(run_id, "finished")


def _placed_review(review: FindingReview, ids: Sequence[int]) -> FindingReview:
    cites = {finding_cite(place): finding_cite(i) for place, i in enumerate(ids, 1)}
    verdict = review.verdict.model_copy(
        update={"cites": tuple(cites[cite] for cite in review.verdict.cites)}
    )
    return review.model_copy(update={"verdict": verdict})


def _placed_synthesis(
    synthesis: StoredSynthesis, ids: Sequence[int]
) -> StoredSynthesis:
    sections = tuple(
        section.model_copy(
            update={"finding_ids": tuple(ids[p - 1] for p in section.finding_ids)}
        )
        for section in synthesis.sections
    )
    headline = tuple(ids[p - 1] for p in synthesis.headline)
    return synthesis.model_copy(update={"sections": sections, "headline": headline})


async def _store_reviews(
    repo: AuditReviewRepository, run_id: UUID, sample: SampleRun, ids: Sequence[int]
) -> None:
    for reviewed in sample.reviews:
        await repo.add_review(
            run_id=run_id,
            finding_id=ids[reviewed.place - 1],
            review=_placed_review(reviewed.review, ids),
            model_id=SAMPLE_MODEL_ID,
        )
    await repo.set_synthesis(run_id, _placed_synthesis(sample.synthesis, ids))
    await repo.set_review(run_id, sample.review_progress)


async def store_sample_run(user_id: UUID) -> SampleRunIds:
    sample = SampleRun.model_validate_json(SAMPLE_PATH.read_text())
    owner = RunOwner(user_id=user_id, conversation_id=uuid4())
    async with async_session_factory() as session:
        await begin_conversation(
            session=session,
            conversation_id=owner.conversation_id,
            user_id=user_id,
            site_id=sample.scope.site_id,
            assistant_id=PATHFINDER_ASSISTANT_ID,
        )
        run_id = await add_run(session, owner=owner, scope=sample.scope)
        await _store_genomes(AuditRepository(session), run_id, sample.genomes)
        ids = await _store_findings(session, run_id, sample.findings)
        await _store_stages(AuditRepository(session), run_id, sample)
        await _store_reviews(AuditReviewRepository(session), run_id, sample, ids)
        await session.commit()
    return SampleRunIds(run_id=run_id, finding_ids=ids)
