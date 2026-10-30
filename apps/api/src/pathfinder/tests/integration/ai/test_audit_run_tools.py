from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.capabilities.refused_calls import CallRefused
from assistant_core.platform.db import async_session_factory
from procrastinate.testing import InMemoryConnector
from pydantic import BaseModel, ConfigDict, TypeAdapter
from pydantic_ai import Agent, DeferredToolRequests, ModelRetry
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import DeferredToolResults, RunContext, ToolDenied
from veupathdb_mcp.audit import GeneId, PseudogeneCallAudit

from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.run_tools import (
    START_TOOL,
    build_run_toolset,
    list_audit_findings_tool,
    list_audit_runs_tool,
    plan_gene_model_audit_tool,
    read_audit_finding,
    read_audit_findings_tool,
    read_audit_run,
    read_audit_run_tool,
    start_gene_model_audit,
)
from pathfinder.ai.audit.verdict_tool import record_gene_model_verdicts
from pathfinder.domain.audit.confirmations import PseudogeneConfirmation
from pathfinder.domain.audit.findings import ConfirmationEvidence
from pathfinder.domain.audit.planning import PlanAsk
from pathfinder.domain.audit.scope import AuditScope, GenePairTarget
from pathfinder.domain.audit.verdicts import (
    GeneModelVerdict,
    evidence_cite,
    finding_cite,
)
from pathfinder.persistence.models import AuditRunRecord
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.persistence.repositories.audit_finding_filter import FindingFilter
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    NewFinding,
    SettledFinding,
)
from pathfinder.platform.errors import NotFoundError
from pathfinder.services.audit.finding_views import FindingQuery
from pathfinder.services.audit.job import start_run
from pathfinder.services.audit.planning import propose_scope
from pathfinder.services.audit.queue import AUDIT_JOB
from pathfinder.services.audit.runs import RunOwner, create_run
from pathfinder.services.gene_records.read import gene_record_url
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests._support.audit_planning import (
    STRAINS,
    faked_site,
    plan_request,
    setting,
)
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.integration.jobs._audit_jobs import (
    TOKEN,
    audit_jobs,
    holding,
    registered,
)

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

_CALL = "start-1"
_STRAIN = "EXA_0001"
_REFERENCE = "EXR_0001"
_GENOME = "Examplea alpha A"
_PAIR = GenePairTarget(check="pseudogene_call", genes=(_STRAIN, _REFERENCE))
_REQUEST = plan_request(STRAINS[0])


class _FindingId(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int


class _Answer(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    finding: _FindingId


class _FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    answer: _Answer


_READS: TypeAdapter[list[_FindingRead]] = TypeAdapter(list[_FindingRead])


@pytest.fixture
def signed_in(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    registered(monkeypatch, TOKEN)
    with holding(TOKEN), sealed_provider_keys(monkeypatch):
        yield


def _deps(owner: RunOwner) -> AuditDeps:
    return AuditDeps(
        site_id="plasmodb",
        user_id=owner.user_id,
        conversation_id=owner.conversation_id,
    )


def _context(owner: RunOwner) -> RunContext[AuditDeps]:
    return run_context_for(_deps(owner), tool_call_id="read-1")


async def _runs(user_id: UUID) -> list[AuditRunRecord]:
    async with async_session_factory() as session:
        return await AuditRepository(session).runs(user_id=user_id)


def _intact() -> PseudogeneCallAudit:
    return PseudogeneCallAudit(
        verdict="INTACT",
        reference_cds_length=900,
        strain_cds_length=900,
        covered=900,
        premature_stops=[],
        residue_differences=0,
        gene_ids=[
            GeneId(given=_STRAIN, resolved=_STRAIN),
            GeneId(given=_REFERENCE, resolved=_REFERENCE),
        ],
        strain_gene=_STRAIN,
        reference_gene=_REFERENCE,
    )


async def _stored_finding(owner: RunOwner) -> tuple[UUID, int]:
    run_id = await create_run(
        owner=owner, scope=AuditScope(site_id="plasmodb", targets=(_PAIR,))
    )
    async with async_session_factory() as session:
        repo = AuditFindingRepository(session)
        await repo.add_findings(
            run_id,
            [NewFinding(genome=_GENOME, target=_PAIR, sampled=True, status="screened")],
        )
        (finding,) = await repo.findings(run_id, FindingFilter())
        await repo.try_finding(finding.id)
        await repo.settle_finding(finding.id, SettledFinding(status="confirmed"))
        await repo.try_evidence(finding.id, "confirmation")
        await repo.save_evidence(
            finding.id,
            ConfirmationEvidence(confirmation=PseudogeneConfirmation(result=_intact())),
            requests=4,
        )
        await session.commit()
    return run_id, finding.id


def _starting(args: dict[str, Any]) -> FunctionModel:
    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        if len(messages) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(tool_name=START_TOOL, args=args, tool_call_id=_CALL)
                ]
            )
        return ModelResponse(parts=[TextPart("answered")])

    return FunctionModel(respond)


async def _parked_then(
    deps: AuditDeps, monkeypatch: pytest.MonkeyPatch, *, approved: bool
) -> tuple[list[ModelMessage], AuditScope]:
    site = faked_site(monkeypatch)
    scope = (await propose_scope(_REQUEST)).scope
    assert scope is not None
    agent = Agent(
        _starting(
            {
                "request": _REQUEST.model_dump(
                    mode="json", by_alias=True, exclude={"site_id"}
                ),
                "scope": scope.model_dump(mode="json", by_alias=True),
            }
        ),
        deps_type=AuditDeps,
        output_type=[str, DeferredToolRequests],
        toolsets=[build_run_toolset()],
    )
    parked = await agent.run("start the audit", deps=deps)
    assert isinstance(parked.output, DeferredToolRequests)
    site.organisms.remove(scope.comparison[-1])
    answer = True if approved else ToolDenied()
    resumed = await agent.run(
        message_history=parked.all_messages(),
        deferred_tool_results=DeferredToolResults(approvals={_CALL: answer}),
        deps=deps,
    )
    return resumed.all_messages(), scope


@pytest.mark.usefixtures("signed_in")
async def test_a_denied_start_writes_no_run(
    in_memory_jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await seed_thread()

    await _parked_then(_deps(owner), monkeypatch, approved=False)

    assert await _runs(owner.user_id) == []
    assert audit_jobs(in_memory_jobs) == []


@pytest.mark.usefixtures("signed_in")
async def test_an_approved_start_queues_the_approved_scope_and_records_it(
    in_memory_jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await seed_thread()
    deps = _deps(owner)

    messages, approved = await _parked_then(deps, monkeypatch, approved=True)

    (run,) = await _runs(owner.user_id)
    (job,) = audit_jobs(in_memory_jobs)
    (started,) = [
        part
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == START_TOOL
    ]
    (fact,) = deps.facts
    assert (run.conversation_id, run.scope) == (owner.conversation_id, approved)
    assert (job["task_name"], started.outcome) == (AUDIT_JOB, "success")
    assert (fact.kind, fact.value("runId"), fact.value("phase")) == (
        "audit_start",
        str(run.id),
        "queued",
    )


@pytest.mark.usefixtures("signed_in")
async def test_a_scope_over_the_cap_is_refused_in_plain_words(
    in_memory_jobs: InMemoryConnector, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await seed_thread()
    three = AuditScope(site_id="plasmodb", genomes=STRAINS[:3], checks=("gene_length",))
    caller = _deps(owner).caller

    with (
        setting(monkeypatch, "AUDIT_MAX_GENOMES", "2"),
        pytest.raises(CallRefused) as refused,
    ):
        await start_gene_model_audit(caller, three)

    assert refused.value.message == (
        "This audit cannot start: an audit reads at most 2 whole genomes, not 3."
    )
    assert await _runs(owner.user_id) == []
    assert audit_jobs(in_memory_jobs) == []


async def test_another_users_run_is_not_found_by_the_tools() -> None:
    owner, stranger = await seed_thread(), await seed_thread()
    run_id, finding_id = await _stored_finding(owner)
    caller = _deps(stranger).caller

    with pytest.raises(CallRefused) as run_refused:
        await read_audit_run(caller, run_id)
    with pytest.raises(CallRefused) as finding_refused:
        await read_audit_finding(caller, run_id, finding_id)

    assert [run_refused.value.message, finding_refused.value.message] == [
        f"no audit run {run_id} here",
        f"no audit run {run_id} here",
    ]


@pytest.mark.usefixtures("signed_in")
async def test_a_run_is_started_again_only_by_its_owner(
    in_memory_jobs: InMemoryConnector,
) -> None:
    owner, stranger = await seed_thread(), await seed_thread()
    run_id, _ = await _stored_finding(owner)
    other_thread = RunOwner(user_id=owner.user_id, conversation_id=uuid4())

    with pytest.raises(NotFoundError):
        await start_run(run_id, stranger)
    with pytest.raises(NotFoundError):
        await start_run(run_id, other_thread)
    started = await start_run(run_id, owner)

    (job,) = audit_jobs(in_memory_jobs)
    assert (started.run_id, job["task_name"]) == (run_id, AUDIT_JOB)


async def test_reading_a_finding_records_its_facts() -> None:
    owner = await seed_thread()
    run_id, finding_id = await _stored_finding(owner)
    ctx = _context(owner)

    returned = await read_audit_findings_tool(ctx, run_id, [finding_id])

    (fact,) = ctx.deps.facts
    (read,) = _READS.validate_python(returned.return_value)
    assert ctx.deps.reads == {
        finding_cite(finding_id),
        evidence_cite(finding_id, "confirmation"),
    }
    assert (fact.kind, read.answer.finding.id) == ("audit_finding", finding_id)
    assert fact.value("evidence.0.payload.confirmation.result.strainCdsLength") == "900"
    assert [(r.record_id, r.url) for r in ctx.deps.records] == [
        (gene, gene_record_url("plasmodb", gene)) for gene in (_STRAIN, _REFERENCE)
    ]


async def test_a_batch_with_an_unknown_finding_holds_no_cite() -> None:
    owner = await seed_thread()
    run_id, finding_id = await _stored_finding(owner)
    ctx = _context(owner)
    verdict = GeneModelVerdict(
        genes=(_STRAIN,),
        model_genome=_GENOME,
        verdict="undecided",
        cause="The stored finding does not settle it.",
        cites=(finding_cite(finding_id),),
    )

    with pytest.raises(CallRefused):
        await read_audit_findings_tool(ctx, run_id, [finding_id, finding_id + 1])
    with pytest.raises(ModelRetry, match=finding_cite(finding_id)):
        await record_gene_model_verdicts(ctx, [verdict])

    assert (ctx.deps.reads, ctx.deps.facts, ctx.deps.records) == (set(), [], [])


async def test_every_audit_read_records_its_fact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    faked_site(monkeypatch)
    owner = await seed_thread()
    run_id, finding_id = await _stored_finding(owner)
    ctx = _context(owner)

    await plan_gene_model_audit_tool(ctx, PlanAsk(genomes=_REQUEST.genomes))
    await list_audit_runs_tool(ctx)
    await read_audit_run_tool(ctx, run_id)
    await list_audit_findings_tool(ctx, run_id, FindingQuery())

    assert [fact.kind for fact in ctx.deps.facts] == [
        "audit_plan",
        "audit_runs",
        "audit_run",
        "audit_findings",
    ]
    plan, runs, run, findings = ctx.deps.facts
    assert (plan.value("scope.genomes.0"), runs.value("runs.0.id")) == (
        STRAINS[0],
        str(run_id),
    )
    assert (run.value("run.id"), findings.value("findings.0.id")) == (
        str(run_id),
        str(finding_id),
    )
    assert [r.record_id for r in ctx.deps.records] == [_STRAIN, _REFERENCE] * 2
    assert ctx.deps.runs == [run_id, run_id]
    assert [
        plan.value("scope.confirmLimit"),
        plan.value("noReference"),
        findings.value("findings.0.screenedGenome"),
        findings.value("findings.0.requests"),
        findings.value("findings.0.target.genes.1"),
        findings.value("siteId"),
    ] == ["150", None, _GENOME, "0", _REFERENCE, "plasmodb"]


async def test_a_plan_records_its_target_genes_and_refuses_an_unheld_genome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    faked_site(monkeypatch)
    ctx = _context(await seed_thread())

    with pytest.raises(CallRefused) as refused:
        await plan_gene_model_audit_tool(ctx, PlanAsk(genomes=("Examplea",)))
    await plan_gene_model_audit_tool(ctx, PlanAsk(targets=(_PAIR,)))

    [targeted] = ctx.deps.facts
    assert refused.value.message.split(". ")[0] == (
        "The planner starts no audit: the site holds no genome named Examplea; the "
        f"organisms its words name are {', '.join(STRAINS[:5])}"
    )
    assert targeted.value("scope.targets.0.genes.0") == _STRAIN
    assert [r.record_id for r in ctx.deps.records] == [_STRAIN, _REFERENCE]
