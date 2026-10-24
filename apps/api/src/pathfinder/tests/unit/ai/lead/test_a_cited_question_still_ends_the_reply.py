"""A reply that ends on a question with a ``cite`` reference before its mark still ends on that question."""

from __future__ import annotations

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.statistic_facts import StatisticFact, StatisticRowFact
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    building_deps,
    kinds,
    reading_deps,
    reply,
)

_FACT = StatisticFact(
    id="stat_ad5c5b01",
    kind="audit_finding",
    title="Finding 1 of audit run a8eb13a5-ccfc-41b2-85d4-f63949ca01ba",
    rows=[StatisticRowFact(name="review.verdict.verdict", value="error", form="word")],
)
_OFFER = (
    "The audit stored one confirmed finding. Would you like me to re-review the "
    "finding the review kept as an error [cite:stat_ad5c5b01.review.verdict.verdict]?"
)


def _cited(deps: LeadDeps) -> LeadDeps:
    deps.state.turn_markers.record_audit_facts([_FACT])
    return deps


def test_an_offer_closed_by_a_cite_is_an_unrecorded_question() -> None:
    deps = _cited(building_deps())

    assert kinds(deps, reply(_OFFER, changed=True, next_state="complete")) == [
        "unrecorded_question"
    ]


def test_a_question_closed_by_a_cite_asks_about_a_failed_check() -> None:
    deps = _cited(reading_deps())
    domain = deps.state.domain
    domain.record_verdict(
        VerificationDigest(
            disposition=PhaseDisposition.DONE,
            prose="Checked.",
            reason="Seven of eight sampled genes are not odorant-binding proteins.",
            success=False,
            gaps=[],
        ),
        revision=strategy_revision(domain.answered_graph),
    )

    assert "failed_check" not in kinds(deps, reply(_OFFER))
