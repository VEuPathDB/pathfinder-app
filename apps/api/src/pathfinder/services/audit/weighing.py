"""The gene records a named finding is weighed by, read from the site, and the weighing its impact
comes from."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from veupathdb_mcp.audit import GeneEvidence
from veupathdb_mcp.tools import audit_gene_evidence

from pathfinder.domain.audit.findings import (
    ConfirmationEvidence,
    EvidencePayload,
    GeneEvidencePayload,
    RelativesEvidence,
    StrainConfirmation,
    classify_confirmation,
)
from pathfinder.domain.audit.rates import (
    GenomeUse,
    Weighing,
    importance_of,
    use_by_role,
    use_of,
)
from pathfinder.domain.audit.scope import GenePairTarget
from pathfinder.persistence.models import AuditEvidenceRecord, AuditFindingRecord
from pathfinder.services.audit.checks import UnitFailure
from pathfinder.services.audit.units import UNIT_FAILURES, failure_status

type References = Mapping[str, bool | None]


@dataclass(frozen=True, kw_only=True)
class Subject:
    finding: AuditFindingRecord
    confirmation: EvidencePayload | None = None
    relatives: EvidencePayload | None = None
    gene_evidence: EvidencePayload | None = None

    @classmethod
    def of(
        cls, finding: AuditFindingRecord, evidence: Sequence[AuditEvidenceRecord]
    ) -> Subject:
        payloads = {e.kind: e.payload for e in evidence if e.finding_id == finding.id}
        return cls(
            finding=finding,
            confirmation=payloads.get("confirmation"),
            relatives=payloads.get("relatives"),
            gene_evidence=payloads.get("gene_evidence"),
        )

    @property
    def genes(self) -> tuple[str, ...]:
        match (self.confirmation, self.relatives, self.finding.target):
            case (
                ConfirmationEvidence(confirmation=StrainConfirmation() as strain),
                _,
                _,
            ) if classify_confirmation(strain).model_role == "reference":
                return (strain.result.reference_gene,)
            case (
                _,
                RelativesEvidence(side="REFERENCE_LONG", reference_gene=gene),
                _,
            ) if self.finding.error_type == "over_extended_model":
                return (gene,)
            case (_, _, GenePairTarget(check="gene_split", genes=genes)):
                return genes
            case _:
                return (self.finding.target.genes[0],)

    def use(self, references: References) -> GenomeUse:
        genome = self.finding.genome
        match self.confirmation:
            case ConfirmationEvidence(confirmation=StrainConfirmation() as strain) if (
                role := classify_confirmation(strain).model_role
            ) is not None:
                return use_by_role(genome, role)
            case _:
                return use_of(genome, reference_strain=references.get(genome))

    def _evidence(self) -> tuple[GeneEvidence, ...] | None:
        match self.gene_evidence:
            case GeneEvidencePayload(genes=genes, evidence=evidence) if (
                genes == self.genes
            ):
                return evidence
            case _:
                return None

    def weighing(self, references: References) -> Weighing | None:
        certainty = self.finding.certainty
        if certainty is None:
            return None
        return Weighing(
            certainty=certainty,
            importance=importance_of(self.genes, self._evidence()),
            use=self.use(references),
        )


async def read_genes(
    site_id: str, genes: Sequence[str]
) -> GeneEvidencePayload | UnitFailure:
    read: list[GeneEvidence] = []
    for gene in genes:
        try:
            read.append(await audit_gene_evidence(site_id, gene))
        except UNIT_FAILURES as exc:
            return UnitFailure(status=failure_status(exc), message=str(exc))
    return GeneEvidencePayload(genes=tuple(genes), evidence=tuple(read))
