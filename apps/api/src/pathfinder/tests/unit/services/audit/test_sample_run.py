"""The shipped sample run parses into the stored shapes and holds the recorded library results."""

from __future__ import annotations

import pytest
from veupathdb_mcp.audit import INTRON_STORE_READS

from pathfinder.services.audit.sample_run import (
    SAMPLE_PATH,
    SampleEvidence,
    SampleRun,
)
from pathfinder.tests._support.audit import PIGA_INTACT
from pathfinder.tests._support.audit_answers import PKAC_INTRONS, organelle, strain
from pathfinder.tests._support.audit_evidence import PIGA_EVIDENCE

SAMPLE = SampleRun.model_validate_json(SAMPLE_PATH.read_text())


def test_the_sample_holds_the_recorded_results() -> None:
    payloads = [
        evidence.payload
        for finding in SAMPLE.findings
        for evidence in finding.evidence
        if evidence.payload is not None
    ]
    results = [p.confirmation.result for p in payloads if p.kind == "confirmation"]
    read = [p.evidence for p in payloads if p.kind == "gene_evidence"]

    assert [results[0], *results[4:]] == [
        PIGA_INTACT,
        strain("STRAIN_SHORT"),
        organelle("SPLIT_AT_JOIN"),
        PKAC_INTRONS,
    ]
    assert read == [(PIGA_EVIDENCE,)]


def test_the_sample_settles_each_finding_as_the_report_page_reads_it() -> None:
    assert [(f.status, f.sampled) for f in SAMPLE.findings] == [
        ("confirmed", True),
        ("confirmed", True),
        ("confirmed", True),
        ("confirmed", True),
        ("unread", True),
        ("unreached", True),
        ("unsampled", False),
        ("confirmed", True),
        ("confirmed", True),
        ("confirmed", True),
    ]
    assert [f.error_type for f in SAMPLE.findings] == [
        "intact_gene_called_pseudogene",
        "truncated_model",
        None,
        None,
        None,
        None,
        None,
        "truncated_model",
        "organelle_split_at_join",
        "missing_exon",
    ]
    assert [w.impact for f in SAMPLE.findings if (w := f.weighing)] == [
        0.5,
        0.25,
        0.25,
        0.25,
        0.25,
    ]


def test_the_sample_reviews_name_findings_by_their_place() -> None:
    assert [r.place for r in SAMPLE.reviews] == [1, 2, 8, 9, 10]
    assert [r.review.verdict.cites for r in SAMPLE.reviews] == [
        ("finding:1",),
        ("finding:2",),
        ("finding:8",),
        ("finding:9",),
        ("finding:10",),
    ]
    assert SAMPLE.synthesis.headline == (1, 8, 9, 10)
    assert [s.finding_ids for s in SAMPLE.synthesis.sections] == [
        (1,),
        (8,),
        (9,),
        (10,),
    ]
    assert (SAMPLE.synthesis.agreement.sampled, SAMPLE.synthesis.agreement.agreed) == (
        2,
        1,
    )


def test_the_sample_stages_count_the_requests_of_a_finished_run() -> None:
    assert [
        (s.name, s.requests, s.store_reads, s.done, s.total) for s in SAMPLE.stages
    ] == [
        ("collect", 4, 0, 3, 3),
        ("screen", 2, 0, 2, 2),
        ("confirm", 9, INTRON_STORE_READS, 6, 8),
        ("tie_break", 6, 0, 1, 3),
    ]
    assert [(g.organism, g.role, len(g.rows)) for g in SAMPLE.genomes] == [
        ("Plasmodium falciparum NF54", "audited", 1),
        ("Plasmodium falciparum Dd2", "audited", 1),
        ("Plasmodium falciparum 3D7", "comparison", 2),
    ]


@pytest.mark.parametrize(
    ("status", "payload", "message"),
    [
        ("stored", None, None),
        ("unread", None, None),
        ("stored", "with a message", "a message"),
    ],
)
def test_sample_evidence_holds_a_payload_or_a_message(
    status: str, payload: str | None, message: str | None
) -> None:
    stored = SAMPLE.findings[0].evidence[0].payload if payload else None

    with pytest.raises(ValueError, match="a payload when stored and a message"):
        SampleEvidence.model_validate(
            {
                "kind": "confirmation",
                "status": status,
                "payload": stored,
                "message": message,
            }
        )
