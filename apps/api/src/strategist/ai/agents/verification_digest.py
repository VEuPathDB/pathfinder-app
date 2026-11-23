"""VERIFY's digest held to the reads of its turn: a statement no read holds is
refused once per check."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import DeferredToolRequests, ModelRetry, RunContext

from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.graph.state import VerificationDigest
from strategist.ai.lead.contract_messages import (
    unbacked_digest_message,
    unread_gene_sentence,
    unretrieved_review_source_sentence,
)
from strategist.ai.lead.deltas import VerificationDelta
from strategist.domain.evidence import (
    VerificationReview,
    WithheldEvidence,
    WithheldKind,
)
from strategist.domain.refusal import Problems, RefusalKey
from strategist.platform.refusals import TURN_REFUSALS_PER_RULE, last_answer
from strategist.services.gene_records.read import gene_record_url


@dataclass(frozen=True)
class _Held:
    withheld: list[WithheldEvidence]
    review: VerificationReview

    @property
    def found(self) -> list[str]:
        return [w.sentence for w in self.withheld]


def _withheld(kind: WithheldKind, sentence: str) -> WithheldEvidence:
    return WithheldEvidence(kind=kind, sentence=sentence)


def _held_review(ctx: RunContext[AgentDeps], digest: VerificationDigest) -> _Held:
    markers = ctx.deps.turn_markers
    review = digest.review
    unread = [
        gene
        for gene in review.sampled_genes
        if markers.retrieved_as(gene_record_url(ctx.deps.site_id, gene.gene_id)) is None
    ]
    unopened = [
        (cited, reference)
        for cited in review.sources
        for reference in cited.references() or [""]
        if not reference or markers.retrieved_as(reference) is None
    ]
    withheld = [
        *(_withheld("sampled_gene", unread_gene_sentence(g.gene_id)) for g in unread),
        *(
            _withheld(
                "source",
                unretrieved_review_source_sentence(reference)
                if reference
                else f"The review cites {cited.label!r}, which carries no url, DOI or PMID.",
            )
            for cited, reference in unopened
        ),
    ]
    dropped = [cited for cited, _ in unopened]
    return _Held(
        withheld,
        review.model_copy(
            update={
                "sampled_genes": [g for g in review.sampled_genes if g not in unread],
                "sources": [c for c in review.sources if c not in dropped],
                "withheld": [*review.withheld, *withheld],
            }
        ),
    )


def hold_the_digest_to_the_evidence(
    ctx: RunContext[AgentDeps], output: VerificationDelta | DeferredToolRequests
) -> VerificationDelta | DeferredToolRequests:
    """Refuse, once per check of the turn, a digest that states what no read of
    the turn holds; past that, take each such item out of the review and record
    it as withheld."""
    if not isinstance(output, VerificationDelta):
        return output
    held = _held_review(ctx, output.digest)
    if not held.withheld:
        return output
    markers = ctx.deps.turn_markers
    key = RefusalKey(
        check="the_digest_to_the_evidence",
        criterion=ctx.deps.verification_scope.check_id,
    )
    said = unbacked_digest_message(held.found)
    charge = markers.answer_ledger.charge(
        Problems.one(key, said), TURN_REFUSALS_PER_RULE
    )
    if not charge.refused.empty and not last_answer(ctx):
        markers.answer_ledger = charge.ledger
        raise ModelRetry(said)
    digest = output.digest.model_copy(update={"review": held.review})
    return output.model_copy(update={"digest": digest})


__all__ = ["hold_the_digest_to_the_evidence"]
