"""The reply of a turn that checked the strategy names every requirement the
check found unmet or unexpressed, and states no sampled-gene count the check's
sample does not hold."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.evidence import (
    EvidenceCard,
    EvidenceVerdict,
    RequirementCheck,
    SampledGene,
    VerificationReview,
)
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import kinds, reply
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_UNMET = RequirementCheck(
    text="at least 2 transmembrane domains",
    turn=1,
    how="search",
    status="unmet",
    note="no step reads transmembrane domains",
)
_MET = RequirementCheck(
    text="with a signal peptide",
    turn=1,
    answered_by=["s1"],
    how="search",
    status="met",
    note="GenesWithSignalPeptide",
)


def _gene(gene_id: str, fits: str) -> SampledGene:
    return SampledGene.model_validate(
        {
            "geneId": gene_id,
            "product": "erythrocyte membrane protein 1",
            "organism": "Plasmodium falciparum 3D7",
            "fits": fits,
            "why": "the product names a membrane protein",
        }
    )


_SAMPLE = [_gene("PF3D7_0100100", "yes"), _gene("PF3D7_0100200", "no")]


def _checked(*, verified_this_turn: bool = True) -> LeadDeps:
    state = pipeline_state(
        user_prompt="P. falciparum 3D7 genes with a signal peptide and at least 2 "
        "transmembrane domains",
        user_message_id=uuid4(),
    )
    review = VerificationReview(requirements=[_MET, _UNMET], sampled_genes=_SAMPLE)
    revision = strategy_revision(None)
    state.domain.record_verdict(
        VerificationDigest(
            disposition=PhaseDisposition.DONE,
            prose="Checked.",
            reason="one requirement unmet",
            success=False,
            review=review,
        ),
        revision=revision,
    )
    state.domain.last_evidence_card = EvidenceCard(
        check_id="call_verify",
        revision=revision,
        site_id="plasmodb",
        checked_at=datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
        site_read="not_read",
        steps=[],
        controls=[],
        citations=[],
        verdict=EvidenceVerdict(supported=False),
        review=review,
    )
    state.turn_markers.verification_dispatched = verified_this_turn
    return lead_deps(state)


def test_a_reply_silent_about_an_unmet_requirement_is_refused() -> None:
    deps = _checked()
    report = reply("The strategy returns the genes with a signal peptide.")

    found = reconcile(report, turn_record(run_context_for(deps)))

    assert [(m.kind, m.sentence) for m in found] == [
        (
            "unreported_requirement",
            (
                "The check reports requirements the strategy does not meet: "
                "'at least 2 transmembrane domains' (unmet: no step reads "
                "transmembrane domains). Your reply does not name them. Name "
                "each as written here, and say what the strategy returns "
                "without it."
            ),
        )
    ]


def test_a_reply_that_names_the_unmet_requirement_stands() -> None:
    report = reply(
        "The strategy does not yet require at least 2 transmembrane domains."
    )

    assert kinds(_checked(), report) == []


def test_a_turn_that_did_not_check_owes_no_requirement() -> None:
    report = reply("The strategy returns the genes with a signal peptide.")

    assert kinds(_checked(verified_this_turn=False), report) == []


def test_a_sampled_gene_count_the_card_does_not_hold_is_refused() -> None:
    deps = _checked()
    report = reply(
        "All 2 sampled genes fit, though at least 2 transmembrane domains is "
        "not yet required."
    )

    found = reconcile(report, turn_record(run_context_for(deps)))

    assert [m.kind for m in found] == ["unbacked_evidence"]
    assert found[0].sentence.startswith(
        "The reply says all 2 sampled genes fit; the check sampled 2 genes: 1 fit, "
        "1 do not fit (`PF3D7_0100200`), 0 unclear."
    )
