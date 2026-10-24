from __future__ import annotations

from collections.abc import Iterable

from pathfinder.domain.audit.confirmations import Confirmation
from pathfinder.domain.audit.findings import (
    ConfirmationEvidence,
    EvidencePayload,
    GeneEvidencePayload,
    RelativesEvidence,
)
from pathfinder.domain.audit.scope import GeneTarget


def named_genes(
    target: GeneTarget, confirmation: Confirmation | None
) -> tuple[str, ...]:
    if confirmation is None:
        return tuple(dict.fromkeys(target.genes))
    resolved = {named.given: named.resolved for named in confirmation.result.gene_ids}
    return tuple(dict.fromkeys(resolved[gene] for gene in target.genes))


def evidence_genes(payloads: Iterable[EvidencePayload]) -> tuple[str, ...]:
    named: list[str] = []
    for payload in payloads:
        match payload:
            case RelativesEvidence(reference_gene=gene):
                named.append(gene)
            case GeneEvidencePayload(genes=genes):
                named.extend(genes)
            case ConfirmationEvidence():
                pass
    return tuple(dict.fromkeys(named))
