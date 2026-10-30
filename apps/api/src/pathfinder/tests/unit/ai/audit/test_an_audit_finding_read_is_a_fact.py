import json
from pathlib import Path
from uuid import UUID

from pathfinder.ai.audit.facts import audit_finding_fact
from pathfinder.domain.read_facts import ReadRow, read_fact
from pathfinder.services.audit.finding_views import FindingDetail

_RECORDED = json.loads(
    (
        Path(__file__).parents[3] / "fixtures/turns/fungidb_audit_finding_read.json"
    ).read_text()
)


def _shown() -> list[ReadRow]:
    detail = FindingDetail.model_validate(_RECORDED["answer"])
    fact = audit_finding_fact(UUID(_RECORDED["run_id"]), detail)
    return read_fact(fact).rows


def test_a_finding_shows_its_error_and_its_stored_certainty() -> None:
    shown = {row.label: row.value for row in _shown()}

    assert (
        shown["finding error title"],
        shown["finding certainty"],
        shown["finding verdict text"],
        shown["finding genome"],
    ) == (
        "Splice site shifted",
        "medium",
        "RNA-seq reads join the exons a few bases away from the annotated splice site",
        "Aspergillus fumigatus Af293",
    )


def test_a_finding_shows_each_piece_of_evidence_it_stored() -> None:
    evidence = [
        row.value
        for row in _shown()
        if row.label in {"evidence kind", "evidence status"}
    ]

    assert evidence == ["confirmation", "stored", "gene evidence", "stored"]


def test_a_finding_shows_no_deep_payload_and_no_link() -> None:
    labels = [row.label for row in _shown()]

    assert (
        any(label.startswith("confirmation") for label in labels),
        any(row.value.startswith("http") for row in _shown()),
    ) == (False, False)
