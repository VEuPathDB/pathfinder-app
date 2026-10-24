"""The fake site and checks, the kept sign-in and the queue steps the audit job tests share."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import httpx
import jwt
import pytest
from assistant_core.platform.db import async_session_factory
from fastmcp.exceptions import ToolError
from procrastinate.testing import InMemoryConnector
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import WDKError
from veupathdb.wdk import VEuPathDBClaims
from veupathdb_mcp.audit import GroupMember, OrthologGroup

from pathfinder.domain.audit.scope import AuditScope, GenePairTarget
from pathfinder.jobs.impls.audit_run_impl import run_audit_job
from pathfinder.persistence.models import AuditFindingRecord
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    FindingFilter,
)
from pathfinder.platform.config import get_settings
from pathfinder.services import wdk_identity
from pathfinder.services.audit import (
    checks,
    collect,
    confirm,
    screen,
    tie_break,
    weighing,
)
from pathfinder.services.audit.queue import AUDIT_JOB
from pathfinder.tests._support.audit import (
    NF54,
    NF54_PIGA,
    P3D7,
    PIGA,
    PIGA_INTACT,
    FakeSite,
    gene_row,
    relative_organisms,
    relatives,
    short_audit,
    split_audit,
)
from pathfinder.tests._support.audit_evidence import evidence_of
from pathfinder.tests._support.audit_genome_screens import no_busco_scores
from pathfinder.tests._support.audit_provenance import served_organisms
from pathfinder.tests._support.veupathdb_tokens import (
    SUBJECT,
    make_signing_key,
    veupathdb_token,
)

_KEY = make_signing_key()
TOKEN = veupathdb_token(_KEY)
EXPIRED_TOKEN = jwt.encode(
    {"sub": SUBJECT, "is_guest": False, "exp": int(time.time()) - 60},
    _KEY,
    algorithm="ES512",
)
SHORT_GROUP = "OG7_0000002"
SPLIT = "NF54_A+NF54_B"
SHORT_RUN_HOURS = "0.003"
ROWS = [
    gene_row("NF54_SHORT", NF54, 200, group=SHORT_GROUP, sequence="chr2"),
    gene_row("NF54_A", NF54, 200, start=10000),
    gene_row("NF54_B", NF54, 210, start=11000),
    gene_row(NF54_PIGA, NF54, None, pseudo=True, group="OG7_0000003", sequence="chr10"),
    gene_row(PIGA, P3D7, 461, group="OG7_0000003", sequence="Pf3D7_10_v3"),
    *relatives(9, 400),
    *relatives(9, 400, group=SHORT_GROUP),
]
SCOPE = AuditScope(
    site_id="plasmodb",
    genomes=(NF54,),
    comparison=relative_organisms(9),
    checks=("gene_length", "gene_split"),
    targets=(GenePairTarget(check="pseudogene_call", genes=(NF54_PIGA, PIGA)),),
)


class Checks:
    def __init__(self, site: FakeSite) -> None:
        self.site = site
        self.asked: list[str] = []
        self.pseudogene_crashes = 0
        self.split_failures: list[BaseException] = []
        self.forbidden = 0
        self.answered_first = 0
        self.evidence_reads: list[str] = []

    def _refused(self) -> None:
        if self.answered_first:
            self.answered_first -= 1
            return
        if self.forbidden:
            self.forbidden -= 1
            raise refused(403)

    async def length(self, site_id: str, gene: str) -> object:
        del site_id
        self.site.tokens.add(veupathdb_auth_token_ctx.get())
        self.asked.append(gene)
        self._refused()
        return short_audit(gene, reference_gene=f"{SHORT_GROUP}_REL0")

    async def split(self, site_id: str, gene_a: str, gene_b: str) -> object:
        del site_id
        self.site.tokens.add(veupathdb_auth_token_ctx.get())
        self.asked.append(f"{gene_a}+{gene_b}")
        self._refused()
        if self.split_failures:
            raise self.split_failures.pop(0)
        return split_audit(gene_a, gene_b, reference_gene="OG7_0000001_REL0")

    async def pseudogene(
        self, site_id: str, strain_gene: str, reference_gene: str
    ) -> object:
        del site_id, reference_gene
        self.asked.append(strain_gene)
        self._refused()
        if self.pseudogene_crashes:
            self.pseudogene_crashes -= 1
            msg = "a library bug"
            raise RuntimeError(msg)
        return PIGA_INTACT

    async def orthologs(self, site_id: str, gene: str) -> OrthologGroup:
        del site_id
        self._refused()
        group = next(row.ortholog_group for row in ROWS if row.gene == gene)
        return OrthologGroup(
            gene=gene,
            members=[
                GroupMember.of_row(row)
                for row in ROWS
                if row.ortholog_group == group and row.gene != gene
            ],
        )

    async def evidence(self, site_id: str, gene: str) -> object:
        del site_id
        self._refused()
        self.evidence_reads.append(gene)
        return evidence_of(gene)


def wire_checks(monkeypatch: pytest.MonkeyPatch) -> Checks:
    site = FakeSite(ROWS)
    fakes = Checks(site)
    monkeypatch.setattr(collect, "genes_of_genome", site.genes_of_genome)
    monkeypatch.setattr(collect, "genome_priorities", no_busco_scores)
    monkeypatch.setattr(collect, "organism_report", served_organisms)
    monkeypatch.setattr(collect, "site_build", site.site_build)
    monkeypatch.setattr(screen, "read_gene_list", site.read_list)
    monkeypatch.setattr(confirm, "record_rows", site.named_rows)
    monkeypatch.setattr(checks, "audit_gene_length", fakes.length)
    monkeypatch.setattr(checks, "audit_gene_split", fakes.split)
    monkeypatch.setattr(checks, "audit_pseudogene_call", fakes.pseudogene)
    monkeypatch.setattr(tie_break, "orthologs_of", fakes.orthologs)
    monkeypatch.setattr(tie_break, "record_rows", site.named_rows)
    monkeypatch.setattr(weighing, "audit_gene_evidence", fakes.evidence)
    return fakes


def registered(monkeypatch: pytest.MonkeyPatch, *tokens: str) -> None:
    async def _claims(token: str, oauth_url: str) -> VEuPathDBClaims | None:
        del oauth_url
        return VEuPathDBClaims(sub="1248677203", is_guest=token not in tokens)

    monkeypatch.setattr(wdk_identity, "validate_oauth_token", _claims)


def short_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIT_RUN_HOURS", SHORT_RUN_HOURS)
    get_settings.cache_clear()


@contextmanager
def holding(token: str | None) -> Iterator[None]:
    reset = veupathdb_auth_token_ctx.set(token)
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(reset)


def audit_jobs(connector: InMemoryConnector) -> list[dict[str, Any]]:
    return [job for job in connector.jobs.values() if job["task_name"] == AUDIT_JOB]


def queued(connector: InMemoryConnector) -> list[dict[str, Any]]:
    return [job for job in audit_jobs(connector) if job["status"] == "todo"]


async def work(connector: InMemoryConnector, job: dict[str, Any]) -> None:
    connector.jobs[job["id"]]["status"] = "doing"
    try:
        with holding(None):
            await run_audit_job(job["args"]["payload"])
    finally:
        connector.jobs[job["id"]]["status"] = "succeeded"


async def work_through(connector: InMemoryConnector) -> int:
    worked = 0
    while waiting := queued(connector):
        (job,) = waiting
        await work(connector, job)
        worked += 1
    return worked


async def sealed(run_id: UUID) -> bytes | None:
    async with async_session_factory() as session:
        return await AuditRepository(session).sealed_token(run_id)


async def split_finding(run_id: UUID) -> AuditFindingRecord:
    async with async_session_factory() as session:
        (split,) = await AuditFindingRepository(session).findings(
            run_id, FindingFilter(checks=("gene_split",))
        )
    return split


def refused(status: int) -> ToolError:
    error = ToolError("plasmodb refused the audit reads")
    error.__cause__ = WDKError(f"GET /record-types -> HTTP {status}", status=status)
    return error


def unanswered() -> ToolError:
    error = ToolError("plasmodb did not answer the audit reads: ConnectError refused")
    error.__cause__ = httpx.ConnectError("connection refused")
    return error
