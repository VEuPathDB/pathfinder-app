"""The conversation keeps every message the researcher wrote for the request it
answers, and a check's review survives the checkpoint beside its verdict."""

from __future__ import annotations

from assistant_core.conversation.serde import build_checkpoint_serde

from pathfinder.ai.graph.state import (
    PhaseDisposition,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.assistants.pathfinder_spec import PATHFINDER_CHECKPOINT_TYPES
from pathfinder.domain.evidence import (
    RequirementCheck,
    SampledGene,
    VerificationReview,
)
from pathfinder.tests._support.separation import ATTACHED_CONTROLS, recorded_offer

_ASKED = "P. falciparum 3D7 genes with a signal peptide"
_ADDED = "Also require at least 2 transmembrane domains."


def _intent(classification: IntentClassification) -> UserIntent:
    return UserIntent(classification=classification, inferred_goal="exported genes")


def _record(domain: StrategyDomainState, text: str) -> None:
    domain.record_intent(_intent(IntentClassification.NEW_STRATEGY), request_text=text)


def test_each_message_is_kept_once_oldest_first() -> None:
    domain = StrategyDomainState()

    _record(domain, _ASKED)
    _record(domain, _ADDED)
    domain.record_intent(
        _intent(IntentClassification.EXTEND_STRATEGY), request_text=_ADDED
    )

    assert domain.request_messages == [_ASKED, _ADDED]


def test_a_request_set_aside_takes_its_messages_and_offers_with_it() -> None:
    offer = recorded_offer()
    domain = StrategyDomainState(
        separation_offers={offer.task_id: offer}, attached_controls=ATTACHED_CONTROLS
    )
    _record(domain, _ASKED)

    domain.set_the_request_aside()

    assert (
        domain.request_messages,
        domain.separation_offers,
        domain.attached_controls,
    ) == ([], {}, None)


def test_a_digest_carries_its_review_through_the_checkpoint() -> None:
    domain = StrategyDomainState()
    review = VerificationReview(
        requirements=[
            RequirementCheck(
                text="with a signal peptide",
                turn=1,
                answered_by=["s1"],
                how="search",
                status="met",
                note="GenesWithSignalPeptide",
            )
        ],
        sampled_genes=[
            SampledGene(
                gene_id="PF3D7_0102200",
                product="ring-infected erythrocyte surface antigen",
                organism="Plasmodium falciparum 3D7",
                fits="yes",
                why="the product is an exported surface antigen",
            )
        ],
    )
    domain.record_verdict(
        VerificationDigest(
            disposition=PhaseDisposition.DONE,
            prose="Checked.",
            reason="ok",
            success=True,
            review=review,
        ),
        revision="rev-1",
    )
    serde = build_checkpoint_serde(PATHFINDER_CHECKPOINT_TYPES)

    restored = serde.loads_typed(serde.dumps_typed(domain))

    assert isinstance(restored, StrategyDomainState)
    assert restored.verification_digest is not None
    assert restored.verification_digest.review == review
