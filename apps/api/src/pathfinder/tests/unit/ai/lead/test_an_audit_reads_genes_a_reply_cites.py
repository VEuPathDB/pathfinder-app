from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic_ai.messages import ToolReturnPart

from pathfinder.ai.audit import run_tools
from pathfinder.ai.audit.facts import AuditRead, audit_run_fact
from pathfinder.ai.lead import lead_audit
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.audit.rates import TargetReport
from pathfinder.domain.audit.run_state import LeftUnits
from pathfinder.domain.audit.scope import AuditScope, SingleGeneTarget
from pathfinder.domain.audit.stages import RunStages
from pathfinder.domain.reply_references import prose_faults, render_reply
from pathfinder.services.audit.review_views import ErrorTypeView, FindingLine
from pathfinder.services.audit.verdicts import AuditCaller
from pathfinder.services.audit.views import AuditRunSummary, AuditRunView
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    user_intent,
)

_RUN = UUID("00000000-0000-4000-8000-000000000002")
_NOW = datetime(2026, 10, 24, tzinfo=UTC)
_PSEUDOGENE = "PfNF54_030008400:pseudogene"
_REFERENCE = "PF3D7_0303300"
_TRUNCATED = "PfNF54_040013300"


def _line(finding_id: int, *genes: str) -> FindingLine:
    return FindingLine(
        id=finding_id,
        genes=list(genes),
        genome="Plasmodium falciparum NF54",
        error_type="intact_gene_called_pseudogene",
        error_title="Intact gene called a pseudogene",
        certainty="high",
        impact=0.25,
        reviewed_impact=0.25,
    )


def _view() -> AuditRunView:
    return AuditRunView(
        run=AuditRunSummary(
            id=_RUN,
            site_id="plasmodb",
            conversation_id=None,
            release=None,
            status="finished",
            phase="finished",
            deadline_at=None,
            genomes=[],
            checks=["gene_length"],
            targets=1,
            created_at=_NOW,
            finished_at=_NOW,
        ),
        scope=AuditScope(
            site_id="plasmodb",
            targets=(SingleGeneTarget(check="gene_length", genes=(_TRUNCATED,)),),
        ),
        stages=RunStages(),
        requests=0,
        store_reads=0,
        unfinished=[],
        genomes=[],
        counts=[],
        rates=[],
        targets=TargetReport(genomes=[], unplaced=0),
        review=None,
        synthesis=None,
        reviewed=1,
        action=None,
        reviews_running=False,
        halt=None,
        left=LeftUnits(genomes=0, findings=0, evidence=0),
        evidence=[],
        error_types=[
            ErrorTypeView(
                error_type="intact_gene_called_pseudogene",
                title="Intact gene called a pseudogene",
                description="The genome encodes the whole gene.",
                count=1,
                genomes=["Plasmodium falciparum NF54"],
                certainty="high",
                cause=None,
                confirmed_by=None,
                reviewed=[_line(13, _PSEUDOGENE, _REFERENCE)],
            )
        ],
        headline=[_line(13, _PSEUDOGENE, _REFERENCE)],
        review_state=None,
        agreement=None,
    )


@pytest.fixture(autouse=True)
def stored_run(monkeypatch: pytest.MonkeyPatch) -> None:
    async def read(caller: AuditCaller, run_id: UUID) -> AuditRunView:
        del caller
        assert run_id == _RUN
        return _view()

    async def listed(caller: AuditCaller) -> list[AuditRunSummary]:
        del caller
        return [_view().run]

    monkeypatch.setattr(run_tools, "read_audit_run", read)
    monkeypatch.setattr(run_tools, "list_audit_runs", listed)


def _audit_deps() -> LeadDeps:
    state = pipeline_state(user_prompt="Is my audit done?", user_message_id=uuid4())
    state.turn_markers.intent_classified = True
    return lead_deps(state, intent=user_intent(IntentClassification.GENE_MODEL_AUDIT))


async def test_a_listed_run_is_not_held_and_a_read_one_is() -> None:
    deps = _audit_deps()
    ctx = run_context_for(deps)

    await lead_audit.list_audit_runs(ctx)
    listed = list(deps.state.turn_markers.audit_runs)
    await lead_audit.read_audit_run(ctx, _RUN)

    assert (listed, deps.state.turn_markers.audit_runs) == ([], [_RUN])


async def test_a_run_read_holds_the_genes_of_its_findings_as_records() -> None:
    state = pipeline_state(user_prompt="Summarize the audit.", user_message_id=uuid4())
    state.turn_markers.intent_classified = True
    deps = lead_deps(state, intent=user_intent(IntentClassification.GENE_MODEL_AUDIT))

    await lead_audit.read_audit_run(run_context_for(deps), _RUN)

    facts = turn_facts(deps, refusal="")
    prose = f"The audit calls [record:{_PSEUDOGENE}] intact."
    assert [r.record_id for r in state.turn_markers.records_retrieved] == [
        _TRUNCATED,
        _PSEUDOGENE,
        _REFERENCE,
    ]
    assert prose_faults(prose, facts) == []
    assert render_reply(prose, facts) == (
        f"The audit calls [{_PSEUDOGENE}](https://qa.plasmodb.org/plasmo.qa/app/"
        f"record/gene/{_PSEUDOGENE}) intact."
    )


def test_the_model_reads_a_run_in_the_spelling_its_references_name() -> None:
    view = _view()
    fact = audit_run_fact(view)
    part = ToolReturnPart(
        tool_name="read_audit_run",
        content=AuditRead[AuditRunView](answer=view, fact_id=fact.id),
        tool_call_id="call_run",
    )

    sent = json.loads(part.model_response_str())
    line = sent["answer"]["headline"][0]

    assert sent["factId"] == fact.id
    assert sent["answer"]["errorTypes"][0]["reviewed"][0]["genes"][0] == (
        fact.value("errorTypes.0.reviewed.0.genes.0")
    )
    assert (line["reviewedImpact"], fact.value("headline.0.reviewedImpact")) == (
        0.25,
        "0.25",
    )
