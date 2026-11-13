from __future__ import annotations

from strategist.ai.audit.run_tools import build_run_toolset
from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from strategist.ai.lead.guarantees import registered_tools
from strategist.ai.lead.intent import (
    ANSWERING_INTENTS,
    BUILDING_INTENTS,
    REQUEST_INTENTS,
    IntentClassification,
)
from strategist.ai.lead.lead_agent import build_lead_agent
from strategist.domain.read_facts import read_fact
from strategist.domain.statistic_facts import StatisticFact, StatisticRowFact
from strategist.domain.strategy.constraints import ConstraintKind
from strategist.domain.turn_facts import TurnFacts
from strategist.tests.unit.ai.lead.conftest import requirement, user_intent

_AUDIT_TOOLS = frozenset(
    {
        "plan_gene_model_audit",
        "start_gene_model_audit",
        "list_audit_runs",
        "read_audit_run",
        "review_audit_run",
        "list_audit_findings",
        "read_audit_findings",
        "investigate_gene_models",
    }
)
_AUDITOR_TOOLS = _AUDIT_TOOLS - {"investigate_gene_models"}


def test_the_lead_registers_no_audit_tool() -> None:
    names = frozenset(registered_tools(build_lead_agent().toolsets))

    assert names & _AUDIT_TOOLS == frozenset()


def test_the_audit_assistant_keeps_the_audit_tools() -> None:
    assert frozenset(build_run_toolset().tools) >= _AUDITOR_TOOLS


def test_the_lead_instructions_name_no_audit_tool() -> None:
    assert [name for name in sorted(_AUDIT_TOOLS) if name in LEAD_INSTRUCTIONS] == []


def test_an_audit_request_is_no_strategy_request() -> None:
    audit = IntentClassification.GENE_MODEL_AUDIT

    assert audit.value == "gene_model_audit"
    assert audit not in BUILDING_INTENTS | REQUEST_INTENTS | ANSWERING_INTENTS


def test_audit_facts_reach_the_wire_capped() -> None:
    fact = StatisticFact(
        id="stat_audit",
        kind="audit_plan",
        title="Audit plan",
        rows=[
            StatisticRowFact(name=f"scope.targets.{k}", value=f"EXA_{k:04d}")
            for k in range(600)
        ],
    )
    facts = TurnFacts(reads=[read_fact(fact)])

    (shown,) = facts.model_dump(by_alias=True, mode="json")["reads"]
    assert (len(shown["rows"]), shown["rows"][0]) == (
        40,
        {"label": "scope targets", "value": "EXA_0000"},
    )


_STRAIN = requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum 3D7")
_KINASES = requirement(ConstraintKind.UNTYPED, "kinases", "protein kinases")


def test_an_audit_turn_records_no_thread_requirement() -> None:
    domain = StrategyDomainState()
    domain.record_intent(
        user_intent(IntentClassification.NEW_STRATEGY, explicit_constraints=[_KINASES]),
        request_text="Find the protein kinases",
    )
    audit = user_intent(
        IntentClassification.GENE_MODEL_AUDIT, explicit_constraints=[_STRAIN]
    ).model_copy(update={"withdrawn_ids": [_KINASES.id]})

    domain.record_intent(
        audit,
        request_text="Audit the gene models of Plasmodium falciparum 3D7 against its relatives",
    )

    assert domain.requirements == [_KINASES]
    assert domain.request_messages == ["Find the protein kinases"]
    assert domain.original_request == "Find the protein kinases"
