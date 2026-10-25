from __future__ import annotations

import re
from collections.abc import Iterator

import httpx
import pytest
from assistant_core.platform.db import async_session_factory
from fastapi import FastAPI
from procrastinate.testing import InMemoryConnector

from pathfinder.ai.audit import start_card
from pathfinder.ai.audit.run_tools import START_TOOL
from pathfinder.ai.models.mock.audit_arcs import NOT_STARTED, START_REPLY
from pathfinder.domain.audit.planning import START_LABEL, PlanRequest, ScopeProposal
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.services.audit.planning import propose_scope
from pathfinder.services.gene_records.read import gene_record_url
from pathfinder.tests._support.audit import seed_thread
from pathfinder.tests._support.audit_planning import STRAINS, faked_site
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
)
from pathfinder.tests.integration.http._lead_audit_turns import (
    GENOME,
    REFERENCE,
    STRAIN,
    approved,
    called,
    domain_of,
    of_type,
    post,
    stored_finding,
    summaries,
    text,
    watched_corrections,
)
from pathfinder.tests.integration.jobs._audit_jobs import (
    TOKEN,
    audit_jobs,
    registered,
)

pytestmark = pytest.mark.usefixtures(
    "patch_app_db_engine", "db_cleaner", "signed_in_to_veupathdb"
)

_AUDIT = f"[[arc:audit]] Audit the gene models of {GENOME} against its relatives"
_FINDING = "[[arc:audit-finding]] Is finding 1 real?"
_SPELLED = "[[arc:audit-finding-spelled]] Is finding 1 real?"
_RENDERED = (
    f"The model of [{STRAIN}]({gene_record_url('plasmodb', STRAIN)}) holds a CDS "
    "of 900 bases."
)
_CALLED_FOR_A_FINDING = [
    "classify_user_intent",
    "list_audit_runs",
    "list_audit_findings",
    "read_audit_findings",
]


@pytest.fixture
def signed_in(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    registered(monkeypatch, TOKEN)
    with sealed_provider_keys(monkeypatch):
        yield


@pytest.fixture
def corrections(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    return watched_corrections(monkeypatch)


@pytest.mark.usefixtures("signed_in")
async def test_the_lead_asks_before_an_audit_starts(
    in_memory_jobs: InMemoryConnector,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    faked_site(monkeypatch)
    owner = await seed_thread()
    thread = owner.conversation_id

    asked = await post(
        app, owner.user_id, in_memory_jobs, chat_post_body(thread, _AUDIT)
    )

    (approval,) = of_type(asked, "tool-approval-request")
    (card,) = of_type(asked, "data-audit-start")
    assert called(asked) == [
        "classify_user_intent",
        "plan_gene_model_audit",
        START_TOOL,
    ]
    assert "Intent: gene_model_audit" in summaries(asked)
    assert START_LABEL in summaries(asked)
    assert card["id"] == approval["toolCallId"]
    assert card["data"]["genomes"] == [GENOME]
    assert text(asked) == START_REPLY
    async with async_session_factory() as session:
        assert await AuditRepository(session).runs(user_id=owner.user_id) == []
    assert audit_jobs(in_memory_jobs) == []

    started = await post(
        app,
        owner.user_id,
        in_memory_jobs,
        approved(thread, approval["toolCallId"], approval["approvalId"]),
    )

    async with async_session_factory() as session:
        (run,) = await AuditRepository(session).runs(user_id=owner.user_id)
    assert run.conversation_id == thread
    assert len(audit_jobs(in_memory_jobs)) == 1
    assert text(started).endswith(f"Audit run {run.id} is planned.")


@pytest.mark.usefixtures("signed_in")
async def test_a_declined_audit_starts_nothing(
    in_memory_jobs: InMemoryConnector,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    faked_site(monkeypatch)
    owner = await seed_thread()
    thread = owner.conversation_id
    asked = await post(
        app, owner.user_id, in_memory_jobs, chat_post_body(thread, _AUDIT)
    )
    (approval,) = of_type(asked, "tool-approval-request")

    declined = await post(
        app,
        owner.user_id,
        in_memory_jobs,
        approved(
            thread, approval["toolCallId"], approval["approvalId"], approved=False
        ),
    )

    async with async_session_factory() as session:
        assert await AuditRepository(session).runs(user_id=owner.user_id) == []
    assert audit_jobs(in_memory_jobs) == []
    assert NOT_STARTED in text(declined)


async def test_a_replan_that_fails_denies_the_start_inside_the_run(
    in_memory_jobs: InMemoryConnector,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    faked_site(monkeypatch)

    async def unreached(request: PlanRequest) -> ScopeProposal:
        del request
        msg = "the site did not answer"
        raise httpx.ConnectError(msg)

    monkeypatch.setattr(start_card, "propose_scope", unreached)
    owner = await seed_thread()

    chunks = await post(
        app,
        owner.user_id,
        in_memory_jobs,
        chat_post_body(owner.conversation_id, _AUDIT),
    )

    warned = [
        c["data"]["summary"]
        for c in chunks
        if c["type"].startswith("data-") and c.get("data", {}).get("status") == "warn"
    ]
    assert of_type(chunks, "data-audit-start") == []
    assert of_type(chunks, "tool-approval-request") == []
    assert len(warned) == 1
    assert warned[0].startswith("PlasmoDB did not answer the planner's reads")
    assert text(chunks).endswith(NOT_STARTED)


async def test_an_audit_request_is_not_the_threads_strategy_request(
    in_memory_jobs: InMemoryConnector,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    faked_site(monkeypatch)
    owner = await seed_thread()

    await post(
        app,
        owner.user_id,
        in_memory_jobs,
        chat_post_body(owner.conversation_id, _AUDIT),
    )

    domain = await domain_of(owner.conversation_id)
    assert domain.user_intent is not None
    assert domain.user_intent.classification.value == "gene_model_audit"
    assert domain.original_request == ""
    assert domain.operational_spec is None


async def test_the_lead_answers_with_the_plans_request_count(
    in_memory_jobs: InMemoryConnector,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    corrections: list[int],
) -> None:
    faked_site(monkeypatch)
    owner = await seed_thread()
    proposal = await propose_scope(PlanRequest(site_id="plasmodb", genomes=STRAINS))
    assert proposal.estimate is not None
    assert proposal.left_out
    prompt = f"[[arc:audit-plan]] Audit the gene models of {', '.join(STRAINS)}"

    chunks = await post(
        app,
        owner.user_id,
        in_memory_jobs,
        chat_post_body(owner.conversation_id, prompt),
    )

    assert called(chunks) == ["classify_user_intent", "plan_gene_model_audit"]
    said = re.fullmatch(
        rf"The run reads the site {proposal.estimate.wdk_requests:,} times, and the "
        r"plan leaves out a genome\[\^(?P<label>n[0-9a-f]{8}-)1\]\.\n\n"
        rf"\[\^(?P=label)1\]: left out: {re.escape(proposal.left_out[0])}",
        text(chunks),
    )
    assert said is not None, text(chunks)
    assert corrections == [0]


async def test_the_lead_answers_a_finding_question_from_the_stored_evidence(
    in_memory_jobs: InMemoryConnector,
    app: FastAPI,
    corrections: list[int],
) -> None:
    owner = await seed_thread()
    await stored_finding(owner)

    chunks = await post(
        app,
        owner.user_id,
        in_memory_jobs,
        chat_post_body(owner.conversation_id, _FINDING),
    )

    assert called(chunks) == _CALLED_FOR_A_FINDING
    assert text(chunks) == _RENDERED
    assert corrections == [0]
    (facts,) = of_type(chunks, "data-facts")
    assert facts["data"]["namedGenes"] == []
    assert [s["recordId"] for s in facts["data"]["sources"]] == [STRAIN, REFERENCE]
    assert facts["data"]["statistics"] == []
    assert (await domain_of(owner.conversation_id)).turn_markers.audit_runs_held


async def test_a_thread_without_a_run_holds_no_audit_runs(
    in_memory_jobs: InMemoryConnector,
    app: FastAPI,
) -> None:
    owner = await seed_thread()

    await post(
        app,
        owner.user_id,
        in_memory_jobs,
        chat_post_body(owner.conversation_id, "[[arc:echo]] hello"),
    )

    domain = await domain_of(owner.conversation_id)
    assert domain.turn_markers.audit_runs_held is False


async def test_a_literal_number_in_a_finding_answer_is_corrected(
    in_memory_jobs: InMemoryConnector,
    app: FastAPI,
    corrections: list[int],
) -> None:
    owner = await seed_thread()
    await stored_finding(owner)

    chunks = await post(
        app,
        owner.user_id,
        in_memory_jobs,
        chat_post_body(owner.conversation_id, _SPELLED),
    )

    assert called(chunks) == _CALLED_FOR_A_FINDING
    assert corrections == [1, 0]
    assert text(chunks) == _RENDERED
