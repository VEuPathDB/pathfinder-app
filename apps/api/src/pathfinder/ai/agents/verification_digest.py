"""VERIFY's digest held to the reads of its turn: a statement no read holds is
refused once per check."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import DeferredToolRequests, ModelRetry, RunContext

from pathfinder.ai.agents.refusal_bound import may_refuse
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
from pathfinder.domain.evidence import (
    RequirementCheck,
    VerificationReview,
    WithheldEvidence,
    WithheldKind,
)
from pathfinder.services.gene_records.read import gene_record_url


@dataclass(frozen=True)
class _Held:
    withheld: list[WithheldEvidence]
    review: VerificationReview

    @property
    def found(self) -> list[str]:
        return [w.sentence for w in self.withheld]


def _withheld(kind: WithheldKind, sentence: str) -> WithheldEvidence:
    return WithheldEvidence(kind=kind, sentence=sentence)


def _held_row(
    row: RequirementCheck, messages: int, known: set[str], held: list[str]
) -> tuple[RequirementCheck | None, list[WithheldEvidence]]:
    if row.turn > messages:
        return None, [
            _withheld(
                "requirement_row", misnumbered_requirement_sentence(row, messages)
            )
        ]
    unknown = [a for a in row.answered_by if a not in known]
    withheld = [
        _withheld("answer", misnamed_answer_sentence(row, answer, held))
        for answer in unknown
    ]
    kept = row.model_copy(
        update={"answered_by": [a for a in row.answered_by if a in known]}
    )
    problem = kept.status_problem
    if not problem:
        return kept, withheld
    said = f"The requirement '{row.text}': {problem}."
    stands = kept.model_copy(
        update={
            "status": "unmet"
            if kept.status == "met" and not kept.answered_by
            else kept.status,
            "answered_by": [] if kept.status == "unmet" else kept.answered_by,
            "no_record_shows_it": False,
            "no_record_judged_it": False,
        }
    )
    return stands, [*withheld, _withheld("status", said)]


def _held_review(ctx: RunContext[AgentDeps], digest: VerificationDigest) -> _Held:
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
    claims = [
        *unbacked_claims(control_claims(text), results),
        *unbacked_sample_claims(sample_claims(text), review.sampled_genes),
    ]
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
    rows = [_held_row(row, messages, known, held) for row in review.requirements]
    withheld = [
        *(_withheld("claim", claim) for claim in claims),
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
        *(w for _, row_withheld in rows for w in row_withheld),
    ]
    dropped = [cited for cited, _ in unopened]
    return _Held(
        withheld,
        review.model_copy(
            update={
                "requirements": [row for row, _ in rows if row is not None],
                "sampled_genes": [g for g in review.sampled_genes if g not in unread],
                "sources": [c for c in review.sources if c not in dropped],
                "withheld": [*review.withheld, *withheld],
            }
        ),
    )


def hold_the_digest_to_the_evidence(
    ctx: RunContext[AgentDeps], output: VerificationDelta | DeferredToolRequests
) -> VerificationDelta | DeferredToolRequests:
    """Refuse, once per check and within the pass's refusal bound, a digest that
    states what no read of the turn holds; past that, take each such item out of
    the review and record it as withheld."""
    if not isinstance(output, VerificationDelta):
        return output
    held = _held_review(ctx, output.digest)
    if not held.withheld:
        return output
    markers = ctx.deps.turn_markers
    check_id = ctx.deps.verification_scope.check_id
    state = ctx.deps.agent_state
    if check_id not in markers.refused_digests and may_refuse(ctx, state.refusals):
        markers.refused_digests.append(check_id)
        state.refusals += 1
        raise ModelRetry(unbacked_digest_message(held.found))
    digest = output.digest.model_copy(update={"review": held.review})
    return output.model_copy(update={"digest": digest})


__all__ = ["hold_the_digest_to_the_evidence"]
