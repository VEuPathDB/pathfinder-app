from __future__ import annotations

from veupathdb_mcp.audit import IntronAudit, OrthologSupport

from pathfinder.domain.audit.check_facts import confirmation_facts
from pathfinder.domain.audit.confirmations import IntronConfirmation
from pathfinder.tests._support.audit import revised
from pathfinder.tests._support.audit_answers import (
    AFU8_INTRONS,
    AGAP3685_INTRONS,
    AGAP7279_INTRONS,
    PKAC_INTRONS,
)
from pathfinder.tests._support.audit_introns import intron_audit


def _pairs(result: IntronAudit) -> list[tuple[str, str]]:
    return [
        (fact.label, fact.value)
        for fact in confirmation_facts(IntronConfirmation(result=result))
    ]


def _introns(result: IntronAudit) -> dict[str, str]:
    return dict(_pairs(result))


def test_an_intron_result_states_the_intron_with_no_read_and_its_junctions() -> None:
    assert _pairs(PKAC_INTRONS) == [
        ("Transcript judged", "PcyM_0736700-t36_1"),
        ("Annotated introns with reads", "2 of 3"),
        ("Intron with no read", "bases 1,381,746 to 1,382,305"),
        (
            "What the evidence shows there",
            "RNA-seq junctions that join an exon the model lacks",
        ),
        (
            "RNA-seq junctions that replace it",
            (
                "1,381,746 to 1,381,886 (1,436 reads; tracks: 1) and "
                "1,382,045 to 1,382,280 (1,686 reads; tracks: 1)"
            ),
        ),
        ("Corrected protein", "341 residues, frame kept"),
        (
            "Orthologs that match",
            "8 for the corrected model, 0 for the annotated one, of 16 read",
        ),
    ]


def test_each_intron_outcome_states_its_evidence() -> None:
    replaced = _introns(AFU8_INTRONS)
    noncanonical = _introns(intron_audit("UNSUPPORTED_NONCANONICAL"))
    retained = _introns(AGAP3685_INTRONS)
    assert (
        replaced["What the evidence shows there"],
        replaced["RNA-seq junctions that replace it"],
        replaced["Corrected protein"],
        replaced["Orthologs that match"],
    ) == (
        "an RNA-seq junction that replaces it",
        "202,209 to 202,266 (18,608 reads; tracks: 1)",
        "93 residues, frame not kept",
        "0 for the corrected model, 8 for the annotated one, of 16 read",
    )
    assert (
        noncanonical["What the evidence shows there"],
        noncanonical["Splice-site bases"],
        noncanonical["Why no correction"],
    ) == (
        "the genome's splice-site bases are not canonical",
        "AT..AC",
        "the correction is not read",
    )
    assert (
        retained["What the evidence shows there"],
        retained["Splice-site bases"],
        retained["Read depth"],
    ) == (
        "RNA-seq reads cover it and none splices it",
        "GT..AG",
        (
            "median 4.17 against an exon median of 7.83 (53%; RETAINED needs 25% or "
            "more), 99% of its bases covered (RETAINED needs 90% or more), track "
            "E-MTAB-2880:E_20h_F (unique reverse)"
        ),
    )
    assert "Evidence not read" not in retained


def test_a_shifted_and_an_unexplained_intron_read_in_words() -> None:
    shifted = _introns(intron_audit("UNSUPPORTED_SHIFTED"))
    unexplained = _introns(intron_audit("UNSUPPORTED_UNEXPLAINED"))
    assert (
        shifted["What the evidence shows there"],
        shifted["RNA-seq junctions that replace it"],
        unexplained["What the evidence shows there"],
        unexplained["RNA-seq junctions that replace it"],
    ) == (
        "an RNA-seq junction a few bases away",
        "1,490 to 1,690 (80 reads; tracks: 1)",
        "no evidence explains it",
        "None found",
    )


def test_an_intron_across_an_assembly_gap_reads_as_unread() -> None:
    facts = _introns(AGAP7279_INTRONS)
    assert (
        facts["What the evidence shows there"],
        facts["Evidence not read"],
        facts["Corrected protein"],
        facts["Orthologs that match"],
    ) == (
        "it spans an assembly gap, so its splice-site bases were not read",
        "the intron 44981063-44981393 spans an assembly gap",
        "Not read",
        "Not read",
    )
    assert "Splice-site bases" not in facts


def test_an_unchecked_intron_result_states_what_it_did_not_read() -> None:
    unchecked = revised(
        intron_audit("NOT_CHECKED"), transcript=None, other_transcripts=None
    )
    assert _pairs(unchecked) == [
        ("Transcript judged", "Not read"),
        ("Annotated introns with reads", "Not read"),
        ("Corrected protein", "Not read"),
        ("Orthologs that match", "Not read"),
    ]


def test_orthologs_not_counted_state_the_reason() -> None:
    reason = "no ortholog protein was read"
    uncounted = revised(PKAC_INTRONS, orthologs=OrthologSupport.not_read(reason))
    assert _introns(uncounted)["Orthologs that match"] == reason
