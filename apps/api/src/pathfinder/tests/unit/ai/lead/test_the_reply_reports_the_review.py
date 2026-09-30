"""A requirement row the check found unmet is a gap the facts part shows, and
the reply names it in words and restates no sampled-gene count."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.caveats import check_gaps
from pathfinder.domain.evidence import (
    EvidenceCard,
    RequirementCheck,
    SampledGene,
    VerificationReview,
)
from pathfinder.domain.strategy.constraints import (
    ConstraintKind,
    provisional_constraints,
)
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.tests.unit.ai.lead._turn_contract_cases import kinds, reply
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

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
    state.domain.requirements = [
        requirement(
            ConstraintKind.OTHER,
            "transmembrane domains",
            "at least 2 transmembrane domains",
        )
    ]
    held = provisional_constraints(state.domain.requirements)
    revision = strategy_revision(None)
    state.domain.record_verdict(
        VerificationDigest(
            disposition=PhaseDisposition.DONE,
            prose="Checked.",
            reason="one requirement unmet",
            success=False,
            review=review,
            gaps=check_gaps(structure=None, words=[], review=review, requirements=held),
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
        review=review,
    )
    state.turn_markers.verification_dispatched = verified_this_turn
    return lead_deps(state)


def test_the_unmet_requirement_is_a_gap_the_facts_part_shows() -> None:
    assert [gap.sentence for gap in turn_facts(_checked()).gaps] == [
        "'at least 2 transmembrane domains': nothing in the strategy answers it"
    ]


def test_a_reply_that_names_the_unmet_requirement_in_words_stands() -> None:
    report = reply("The strategy does not yet require the transmembrane domains.")

    assert kinds(_checked(), report) == []


def test_a_reply_with_a_sample_size_the_facts_lack_is_refused() -> None:
    report = reply("All 3 sampled genes fit the signal peptide.")

    assert kinds(_checked(), report) == ["fact_outside_the_block"]
