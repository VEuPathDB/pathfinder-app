"""A finished audit run of synthetic findings, a recorded reviewer model and the review queue steps the review job tests share."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager, contextmanager
from typing import Any
from uuid import UUID

import pytest
from assistant_core.mcp.admission import (
    AdmissionRecord,
    AdmittedSources,
    install_admitted_sources,
)
from assistant_core.platform.db import async_session_factory
from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from procrastinate.testing import InMemoryConnector
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings

from pathfinder.ai.audit import review
from pathfinder.ai.audit.mock import build_review_mock
from pathfinder.domain.audit.findings import Certainty, RelativesEvidence
from pathfinder.domain.audit.rates import GenomeUse, Importance, Weighing
from pathfinder.domain.audit.scope import AuditScope, SingleGeneTarget
from pathfinder.jobs.impls.audit_review_impl import run_review_job
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
    NewFinding,
    SettledFinding,
)
from pathfinder.persistence.repositories.audit_weighings import (
    AuditWeighingRepository,
)
from pathfinder.platform.config import get_settings
from pathfinder.platform.tool_sources import (
    RESEARCH_MCP_PART_NAMESPACE,
    RESEARCH_MCP_SOURCE_ID,
)
from pathfinder.services.audit.queue import AUDIT_REVIEW_JOB
from pathfinder.services.audit.runs import RunOwner, create_run
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests.integration.http._wdk_mcp_double import serve_mcp

GENOME = "Examplea alpha A"
RESEARCH_TOKEN = "research-mcp-client-secret-0123456789abcdef"
_READ = ToolAnnotations(readOnlyHint=True, openWorldHint=True)


def weighed(
    gene: str, certainty: Certainty, *, cited: bool, reference: bool
) -> Weighing:
    return Weighing(
        certainty=certainty,
        importance=Importance(genes=(gene,), source="cited" if cited else "uncited"),
        use=GenomeUse(genome=GENOME, source="model_role", reference=reference),
    )


def gene(number: int) -> str:
    return f"EXA_{number:04d}"


def target(number: int) -> SingleGeneTarget:
    return SingleGeneTarget(check="gene_length", genes=(gene(number),))


async def add_named(run_id: UUID, weighings: dict[int, Weighing]) -> dict[str, int]:
    async with async_session_factory() as session:
        findings = AuditFindingRepository(session)
        await findings.add_findings(
            run_id,
            [
                NewFinding(
                    genome=GENOME, target=target(n), sampled=True, status="screened"
                )
                for n in weighings
            ],
        )
        stored = {
            row.target.genes[0]: row.id
            for row in await findings.findings(run_id, FindingFilter())
        }
        for number, weighing in weighings.items():
            finding_id = stored[gene(number)]
            await findings.try_finding(finding_id)
            await findings.settle_finding(
                finding_id,
                SettledFinding(
                    status="confirmed",
                    error_type="truncated_model",
                    certainty=weighing.certainty,
                ),
            )
            await AuditWeighingRepository(session).set_impact(finding_id, weighing)
            await findings.try_evidence(finding_id, "relatives")
            await findings.save_evidence(
                finding_id,
                RelativesEvidence(
                    reference_gene=f"EXB_{number:04d}",
                    reference_length=400,
                    model_length=200,
                    relatives_median=400.0,
                ),
                requests=1,
            )
        await session.commit()
    return stored


async def finished_run(
    weighings: dict[int, Weighing],
) -> tuple[RunOwner, UUID, dict[str, int]]:
    owner = await seed_thread()
    scope = AuditScope(site_id="plasmodb", targets=tuple(target(n) for n in weighings))
    run_id = await create_run(owner=owner, scope=scope)
    stored = await add_named(run_id, weighings)
    async with async_session_factory() as session:
        await AuditRepository(session).set_status(run_id, "finished")
        await session.commit()
    return owner, run_id, stored


def high(number: int) -> Weighing:
    return weighed(gene(number), "high", cited=True, reference=True)


def review_jobs(connector: InMemoryConnector) -> list[dict[str, Any]]:
    return [j for j in connector.jobs.values() if j["task_name"] == AUDIT_REVIEW_JOB]


def queued_reviews(connector: InMemoryConnector) -> list[dict[str, Any]]:
    return [job for job in review_jobs(connector) if job["status"] == "todo"]


async def work_review(connector: InMemoryConnector, job: dict[str, Any]) -> None:
    connector.jobs[job["id"]]["status"] = "doing"
    try:
        await run_review_job(job["args"]["payload"])
    finally:
        connector.jobs[job["id"]]["status"] = "succeeded"


async def work_reviews(connector: InMemoryConnector) -> int:
    worked = 0
    while waiting := queued_reviews(connector):
        (job,) = waiting
        await work_review(connector, job)
        worked += 1
    return worked


class RecordedReviewer(WrapperModel):
    def __init__(self, wrapped: Model) -> None:
        super().__init__(wrapped)
        self.requests: list[list[ModelMessage]] = []
        self.fail_at = 0
        self.failure: BaseException | None = None

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        self.requests.append(list(messages))
        if self.failure is not None and len(self.requests) == self.fail_at:
            raise self.failure
        return await super().request(messages, model_settings, model_request_parameters)

    def runs(self) -> list[list[ModelMessage]]:
        return [messages for messages in self.requests if len(messages) == 1]


def recorded_reviewer(monkeypatch: pytest.MonkeyPatch) -> RecordedReviewer:
    recorder = RecordedReviewer(build_review_mock())
    monkeypatch.setattr(review, "review_model", lambda model_id: recorder)
    return recorder


@asynccontextmanager
async def served_research(answer: dict[str, Any]) -> AsyncIterator[str]:
    async def literature_search(query: str) -> dict[str, Any]:
        """Search scientific literature.

        Args:
            query: Literature search query.
        """
        del query
        return answer

    source: FastMCP[None] = FastMCP(name="veupathdb-research-mcp-double")
    source.tool(literature_search, annotations=_READ)
    async with serve_mcp(source) as endpoint:
        yield endpoint


@contextmanager
def admitted_research(endpoint: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    install_admitted_sources(
        AdmittedSources(
            records=(
                AdmissionRecord(
                    source_id=RESEARCH_MCP_SOURCE_ID,
                    endpoint=endpoint,
                    credential_mode="service",
                    part_namespace=RESEARCH_MCP_PART_NAMESPACE,
                    max_call_seconds=30,
                ),
            ),
        ),
    )
    monkeypatch.setenv("RESEARCH_MCP_SERVICE_TOKENS", f"pathfinder:{RESEARCH_TOKEN}")
    get_settings.cache_clear()
    try:
        yield
    finally:
        install_admitted_sources(AdmittedSources())
        get_settings.cache_clear()


def ids_in(stored: dict[str, int], numbers: Sequence[int]) -> list[int]:
    return [stored[gene(n)] for n in numbers]
