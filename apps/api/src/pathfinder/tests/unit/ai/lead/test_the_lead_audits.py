from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import PendingApproval
from pydantic_ai import DeferredToolRequests
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import ToolDenied

from pathfinder.ai.audit.run_tools import START_TOOL
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.card_contract import hold_the_contract_on_a_card
from pathfinder.ai.lead.card_reply import CARD_NOT_SHOWN
from pathfinder.ai.lead.guarantees import registered_tools
from pathfinder.ai.lead.intent import (
    ANSWERING_INTENTS,
    BUILDING_INTENTS,
    REQUEST_INTENTS,
    IntentClassification,
)
from pathfinder.ai.lead.intent_gate import (
    tools_the_turn_offers,
    withhold_by_turn_state,
)
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.reply_references import render_reply
from pathfinder.domain.statistic_facts import StatisticFact, StatisticRowFact
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.tests._support.audit_planning import faked_site
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    OfferedTools,
    final_result_part,
    lead_deps,
    pipeline_state,
    requirement,
    user_intent,
)

_AUDIT_READS = frozenset(
    {
        "plan_gene_model_audit",
        "list_audit_runs",
        "read_audit_run",
        "list_audit_findings",
        "read_audit_findings",
        "review_audit_run",
        "investigate_gene_models",
    }
)
_AUDIT_TOOLS = _AUDIT_READS | frozenset({START_TOOL})


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> None:
    faked_site(monkeypatch)


def _names() -> frozenset[str]:
    return frozenset(registered_tools(build_lead_agent().toolsets))


def _classified(classification: IntentClassification | None) -> LeadDeps:
    state = pipeline_state(user_prompt="audit it", user_message_id=uuid4())
    intent = None if classification is None else user_intent(classification)
    state.turn_markers.intent_classified = intent is not None
    return lead_deps(state, intent=intent)


def test_an_audit_request_is_no_strategy_request() -> None:
    audit = IntentClassification.GENE_MODEL_AUDIT

    assert audit.value == "gene_model_audit"
    assert audit not in BUILDING_INTENTS | REQUEST_INTENTS | ANSWERING_INTENTS


def test_the_lead_registers_the_audit_tools() -> None:
    assert _names() & _AUDIT_TOOLS == _AUDIT_TOOLS
    assert frozenset({START_TOOL}) == frozenset({START_TOOL})


def _offered(deps: LeadDeps) -> frozenset[str]:
    return tools_the_turn_offers(deps, _names()) & _AUDIT_TOOLS


@pytest.mark.parametrize(
    "classification",
    [None, *IntentClassification],
)
def test_every_turn_reaches_the_audit_tools_whatever_its_classification(
    classification: IntentClassification | None,
) -> None:
    assert _offered(_classified(classification)) == _AUDIT_TOOLS


def _listed(deps: LeadDeps) -> frozenset[str]:
    seen = OfferedTools()

    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages
        seen.record(info)
        args = {
            "prose": "A plain answer.",
            "nextState": "await_user",
            "strategyChanged": False,
        }
        return ModelResponse(parts=[final_result_part(args)])

    asyncio.run(build_lead_agent().run("q", deps=deps, model=FunctionModel(answer)))
    return frozenset(seen.listed[0]) & _AUDIT_TOOLS


def test_a_strategy_turn_sends_every_audit_tool_schema() -> None:
    assert _listed(_classified(IntentClassification.NEW_STRATEGY)) == _AUDIT_TOOLS


def test_audit_facts_render_references_and_stay_off_the_wire() -> None:
    fact = StatisticFact(
        id="stat_audit",
        kind="audit_plan",
        title="Audit plan",
        rows=[
            StatisticRowFact(name=f"scope.targets.{k}", value=f"EXA_{k:04d}")
            for k in range(600)
        ],
    )
    facts = TurnFacts(audit_statistics=[fact])

    assert facts.model_dump(by_alias=True, mode="json") == TurnFacts().model_dump(
        by_alias=True, mode="json"
    )
    assert render_reply("It holds [stat:stat_audit.scope.targets.599].", facts) == (
        "It holds EXA_0599."
    )


def _answering(classification: IntentClassification | None) -> LeadDeps:
    deps = _classified(classification)
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_start", tool_name=START_TOOL
    )
    return deps


def _started(deps: LeadDeps) -> LeadDeps:
    started = StatisticFact(
        id="stat_start", kind="audit_start", title="Audit run started", rows=[]
    )
    deps.state.turn_markers.record_audit_facts([started])
    return deps


def test_a_turn_that_started_an_audit_reaches_no_tool() -> None:
    deps = _started(_answering(IntentClassification.APPROVAL))

    assert tools_the_turn_offers(deps, _names()) == frozenset()


def test_a_turn_that_started_an_audit_withholds_every_read() -> None:
    names = _names()
    deps = _started(_classified(IntentClassification.GENE_MODEL_AUDIT))

    withheld = withhold_by_turn_state(run_context_for(deps), sorted(names))

    assert withheld == names


def test_a_start_cards_reply_is_held_to_the_references() -> None:
    deps = _classified(IntentClassification.GENE_MODEL_AUDIT)
    call = ToolCallPart(
        tool_name=START_TOOL,
        args={"reply": "The run reads the site 900 times.", "request": {}},
        tool_call_id="call_start",
    )

    results = hold_the_contract_on_a_card(
        run_context_for(deps), DeferredToolRequests(approvals=[call])
    )

    assert results is not None
    denial = results.approvals["call_start"]
    assert isinstance(denial, ToolDenied)
    assert "``900``" in denial.message
    assert denial.message.endswith(f"{CARD_NOT_SHOWN} Answer again with the card.")


_STRAIN = requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum 3D7")
_KINASES = requirement(ConstraintKind.OTHER, "kinases", "protein kinases")


def test_an_audit_turn_records_no_thread_requirement() -> None:
    domain = StrategyDomainState()
    domain.record_intent(
        user_intent(IntentClassification.NEW_STRATEGY, explicit_constraints=[_KINASES]),
        request_text="Find the protein kinases",
    )
    audit = user_intent(
        IntentClassification.GENE_MODEL_AUDIT, explicit_constraints=[_STRAIN]
    ).model_copy(update={"withdrawn": [_KINASES]})

    domain.record_intent(
        audit,
        request_text="Audit the gene models of Plasmodium falciparum 3D7 against its relatives",
    )

    assert domain.requirements == [_KINASES]
    assert domain.request_messages == ["Find the protein kinases"]
    assert domain.original_request == "Find the protein kinases"
