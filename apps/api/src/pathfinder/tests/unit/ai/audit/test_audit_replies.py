from __future__ import annotations

from uuid import UUID

from pathfinder.ai.audit.facts import plan_fact, start_fact
from pathfinder.domain.audit.findings import AuditOutcome, FindingCounts
from pathfinder.domain.audit.planning import (
    PlanRequest,
    RunEstimate,
    ScopeProposal,
)
from pathfinder.domain.audit.scope import AuditScope
from pathfinder.domain.reply_references import prose_faults, render_reply
from pathfinder.domain.statistic_facts import StatisticFact, StatisticRowFact
from pathfinder.domain.turn_facts import TurnFacts

_RUN = UUID("0b6f3a52-6a1e-4c55-9a62-1f1d2a3b4c5d")
_GENOME = "Examplea alpha A"


def _facts() -> TurnFacts:
    started = start_fact(
        AuditOutcome(
            run_id=_RUN,
            status="planned",
            release=None,
            requests=0,
            unfinished=(),
            counts=FindingCounts(),
            failed_genomes=(),
            unreached_genomes=(),
            unread_genomes=(),
        )
    )
    planned = plan_fact(
        ScopeProposal(
            request=PlanRequest(site_id="plasmodb", genomes=(_GENOME,)),
            scope=AuditScope(
                site_id="plasmodb", genomes=(_GENOME,), checks=("gene_length",)
            ),
            estimate=RunEstimate(
                wdk_requests=40,
                store_reads=2,
                hours=0.5,
                hours_at_most=6,
                model_reviews=60,
            ),
            no_reference="no genome of Examplea alpha is marked a reference strain",
        )
    )
    return TurnFacts(statistics=[started, planned])


def test_a_run_id_and_a_check_name_by_reference_pass_the_checker() -> None:
    facts = _facts()
    started, planned = facts.statistics
    prose = (
        f"Audit run [stat:{started.id}.runId] runs the "
        f"[stat:{planned.id}.scope.checks.0] check."
    )

    assert prose_faults(prose, facts) == []
    assert render_reply(prose, facts) == (
        f"Audit run {_RUN} runs the gene length check."
    )


def test_a_run_id_written_out_is_pointed_at_its_reference() -> None:
    facts = _facts()
    started, planned = facts.statistics

    faults = prose_faults(f"Audit run {_RUN} runs the gene_length check.", facts)

    assert [(f.token, f.kind, f.references) for f in faults] == [
        (str(_RUN), "identifier", (f"[stat:{started.id}.runId]",)),
        ("gene_length", "identifier", (f"[stat:{planned.id}.scope.checks.0]",)),
    ]


def test_a_bare_count_keeps_its_count_reference_beside_an_equal_statistic() -> None:
    trend = StatisticFact(
        id="stat_aaaa1111",
        kind="trend",
        title="Trend",
        rows=[StatisticRowFact(name="samples", value="12")],
    )
    facts = TurnFacts(statistics=[trend], root_count=12)

    (fault,) = [
        f
        for f in prose_faults("The strategy returns 12 genes.", facts)
        if f.token == "12"
    ]

    assert fault.references == ("[root]", "[stat:stat_aaaa1111.samples]")
