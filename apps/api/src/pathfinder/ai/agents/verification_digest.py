"""VERIFY's digest held to the reads of its turn: a statement no read holds is
refused once per check."""

from __future__ import annotations

from pydantic_ai import DeferredToolRequests, ModelRetry, RunContext

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.state import VerificationDigest
from pathfinder.ai.lead.contract_messages import (
    misnamed_answer_sentence,
    misnumbered_requirement_sentence,
    unbacked_digest_message,
    unread_gene_sentence,
    unretrieved_review_source_sentence,
)
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.evidence_claims import (
    backing_results,
    control_claims,
    sample_claims,
    unbacked_claims,
    unbacked_sample_claims,
)
from pathfinder.services.gene_records.read import gene_record_url


def _unbacked_in(ctx: RunContext[AgentDeps], digest: VerificationDigest) -> list[str]:
    """Every statement of the digest that no read of this turn holds."""
    markers = ctx.deps.turn_markers
    scope = ctx.deps.verification_scope
    review = digest.review
    text = "\n".join([digest.prose, *digest.key_findings])
    results = backing_results(
        (run.evidence for run in markers.control_tests), scope.last_card, ()
    )
    messages = max(len(scope.messages), 1)
    graph = ctx.deps.strategy_session.get_graph(None)
    held = sorted(graph.steps) if graph is not None else []
    known = {
        *held,
        *(c.id for c in ctx.deps.agent_state.operational_spec_draft.criteria),
    }
    return [
        *unbacked_claims(control_claims(text), results),
        *unbacked_sample_claims(sample_claims(text), review.sampled_genes),
        *(
            unread_gene_sentence(gene.gene_id)
            for gene in review.sampled_genes
            if markers.retrieved_as(gene_record_url(ctx.deps.site_id, gene.gene_id))
            is None
        ),
        *(
            unretrieved_review_source_sentence(reference)
            for cited in review.sources
            for reference in cited.references()
            if markers.retrieved_as(reference) is None
        ),
        *(
            misnumbered_requirement_sentence(row, messages)
            for row in review.requirements
            if row.turn > messages
        ),
        *(
            misnamed_answer_sentence(row, answer, held)
            for row in review.requirements
            for answer in row.answered_by
            if answer not in known
        ),
    ]


def hold_the_digest_to_the_evidence(
    ctx: RunContext[AgentDeps], output: VerificationDelta | DeferredToolRequests
) -> VerificationDelta | DeferredToolRequests:
    """Refuse, once per check, a digest that states what no read of the turn holds."""
    if not isinstance(output, VerificationDelta):
        return output
    markers = ctx.deps.turn_markers
    check_id = ctx.deps.verification_scope.check_id
    if check_id in markers.refused_digests:
        return output
    found = _unbacked_in(ctx, output.digest)
    if not found:
        return output
    markers.refused_digests.append(check_id)
    raise ModelRetry(unbacked_digest_message(found))


__all__ = ["hold_the_digest_to_the_evidence"]
