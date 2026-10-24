from __future__ import annotations

from pathfinder.domain.audit.confirmations import PseudogeneConfirmation
from pathfinder.domain.audit.findings import (
    ConfirmationEvidence,
    EvidencePayload,
    EvidenceStatus,
    GeneEvidencePayload,
    RelativesEvidence,
)
from pathfinder.persistence.models import AuditEvidenceRecord
from pathfinder.services.audit.finding_views import stored_facts
from pathfinder.tests._support.audit import PIGA, PIGA_INTACT
from pathfinder.tests._support.audit_evidence import PIGA_EVIDENCE

_RELATIVES = RelativesEvidence(
    reference_gene=PIGA,
    reference_length=461,
    model_length=461,
    relatives_median=None,
)
_RECORDS = GeneEvidencePayload(genes=(PIGA,), evidence=(PIGA_EVIDENCE,))


def _record(payload: EvidencePayload, status: EvidenceStatus) -> AuditEvidenceRecord:
    return AuditEvidenceRecord(
        finding_id=1,
        kind=payload.kind,
        status=status,
        payload=payload if status == "stored" else None,
        requests=1,
        attempts=1,
        stopped=0,
        message=None,
    )


def test_the_stored_evidence_reads_as_facts_in_kind_order() -> None:
    confirmation = ConfirmationEvidence(
        confirmation=PseudogeneConfirmation(result=PIGA_INTACT)
    )
    groups = stored_facts(
        [
            _record(_RECORDS, "stored"),
            _record(_RELATIVES, "unreached"),
            _record(confirmation, "stored"),
        ]
    )
    assert [(group.kind, group.facts[0].label) for group in groups] == [
        ("confirmation", "Reference coding sequence"),
        ("gene_evidence", "PF3D7_1032400 citations"),
    ]


def test_a_stored_relatives_read_sits_before_the_gene_records() -> None:
    groups = stored_facts([_record(_RECORDS, "stored"), _record(_RELATIVES, "stored")])
    assert [group.kind for group in groups] == ["relatives", "gene_evidence"]
