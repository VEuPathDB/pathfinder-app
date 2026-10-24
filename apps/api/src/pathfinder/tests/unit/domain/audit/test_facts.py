from __future__ import annotations

from pathfinder.domain.audit.check_facts import confirmation_facts, evidence_facts
from pathfinder.domain.audit.confirmations import (
    FusionConfirmation,
    IntronConfirmation,
    LengthConfirmation,
    MissingGeneConfirmation,
    OrganelleConfirmation,
    PseudogeneConfirmation,
    SelenoproteinConfirmation,
    StrainConfirmation,
)
from pathfinder.domain.audit.facts import (
    Fact,
    evidence_summary,
    gene_evidence_facts,
    relatives_facts,
    runs_text,
)
from pathfinder.domain.audit.findings import GeneEvidencePayload, RelativesEvidence
from pathfinder.tests._support.audit import PIGA, PIGA_INTACT, SELK_STOPS, short_audit
from pathfinder.tests._support.audit_answers import (
    AFU8_INTRONS,
    AGAP3685_INTRONS,
    AGAP7279_INTRONS,
    PKAC_INTRONS,
    fusion,
    missing,
    organelle,
    strain,
)
from pathfinder.tests._support.audit_evidence import PIGA_EVIDENCE
from pathfinder.tests._support.audit_introns import intron_audit
from pathfinder.tests._support.audit_wire import DD2_YIP1, P3D7_YIP1


def _pairs(facts: tuple[Fact, ...]) -> list[tuple[str, str]]:
    return [(fact.label, fact.value) for fact in facts]


def _introns(confirmation: IntronConfirmation) -> dict[str, str]:
    return dict(_pairs(confirmation_facts(confirmation)))


def test_a_pseudogene_call_states_its_rebuilt_sequence() -> None:
    assert _pairs(confirmation_facts(PseudogeneConfirmation(result=PIGA_INTACT))) == [
        ("Reference coding sequence", "1,386 bases"),
        ("Strain sequence rebuilt through it", "1,386 bases"),
        ("Bases that match the reference", "1,386 of 1,386"),
        ("Stops inside the rebuilt protein", "None"),
        ("Amino acids that differ from the reference", "0"),
    ]


def test_a_strain_model_states_the_residues_it_lacks_and_its_relatives() -> None:
    facts = _pairs(
        confirmation_facts(StrainConfirmation(result=strain("STRAIN_SHORT")))
    )
    assert facts[:5] == [
        ("Strain model PcyM_0736700", "280 residues"),
        ("Reference model PCYB_074210", "341 residues"),
        ("Reference residues the strain model lacks", "41 to 100"),
        ("Strain residues the reference lacks", "None"),
        (
            "The strain's DNA over the lost part",
            "The genome's DNA encodes the part the model lacks",
        ),
    ]
    named = dict(facts)
    assert (
        named["Related genomes"],
        named["Related genomes from"],
        named["Median of the related genomes"],
    ) == (
        "Plasmodium relative0 X (335 residues) and Plasmodium relative1 X (345 residues)",
        "The same genus",
        "340 residues",
    )


def test_an_organelle_gene_states_where_it_is_whole() -> None:
    assert _pairs(
        confirmation_facts(OrganelleConfirmation(result=organelle("SPLIT_AT_JOIN")))
    ) == [
        ("Sequence", "CM019798.1, 6,054 bases"),
        ("Best whole copy on the linear sequence", "274 of 376 residues"),
        ("Best copy across the join", "376 of 376 residues"),
        ("Bases the two ends share", "87, with 0 mismatches"),
        ("Genetic code", "Standard (inferred)"),
    ]


def test_a_missing_gene_and_a_selenoprotein_end_state_what_the_dna_holds() -> None:
    absent = _pairs(
        confirmation_facts(
            MissingGeneConfirmation(result=missing("IN_DNA_UNANNOTATED"))
        )
    )
    assert absent[:7] == [
        ("Gene looked for", "TGARI_257090, 359 residues"),
        ("Genome it is absent from", "Toxoplasma gondii GT1"),
        ("Conserved neighbours", "TGGT1_257070 and TGGT1_257100 on TGGT1_chrVIIb"),
        ("Where the DNA encodes it", "34 of 34 windows, bases 4,156,680 to 4,157,729"),
        (
            "Open reading frame there",
            "196 residues, 196 identical to the gene looked for",
        ),
        ("Stops in the frame", "at residue 163"),
        ("The frame is whole", "No"),
    ]
    assert _pairs(confirmation_facts(SelenoproteinConfirmation(result=SELK_STOPS))) == [
        ("Residues the genome encodes after the model's end", "*G*"),
        ("The reference's last residues (U is selenocysteine)", "UG"),
        ("Identity of the two ends", "100%"),
        ("The model's stop sits where the reference has selenocysteine", "Yes"),
    ]


def test_a_length_check_states_its_windows_in_words() -> None:
    short = short_audit(DD2_YIP1, reference_gene=P3D7_YIP1)
    facts = dict(
        _pairs(
            confirmation_facts(LengthConfirmation(check="gene_length", result=short))
        )
    )
    assert (
        facts["Windows of the reference protein"],
        facts["Ortholog group median"],
        facts["Length against the median"],
    ) == (
        "19: 12 in the model, 7 encoded on the same strand outside the model",
        "200 residues over 10 organisms",
        "0.6",
    )


def test_a_merge_states_its_extra_part_and_the_neighbour_it_matches() -> None:
    merged = fusion("EXTRA_MATCHES_NEIGHBOUR")
    facts = dict(_pairs(confirmation_facts(FusionConfirmation(result=merged))))
    assert (
        facts["Extra residues"],
        facts["Partner gene"],
        facts["Windows matching a neighbour"],
        facts["Product"],
    ) == (
        "1 to 220, 221 to 270 and 271 to 690",
        "PCOAH_00051820",
        "56 of 66",
        "26S protease regulatory subunit 8",
    )


def test_runs_read_as_spans_joined_in_words() -> None:
    assert [runs_text(runs) for runs in ([], [(1, 9)], [(1, 9), (20, 1200)])] == [
        "None",
        "1 to 9",
        "1 to 9 and 20 to 1,200",
    ]


def test_an_intron_result_states_the_intron_with_no_read_and_its_junctions() -> None:
    facts = _introns(IntronConfirmation(result=PKAC_INTRONS))
    assert facts == {
        "Transcript judged": "PcyM_0736700-t36_1",
        "Annotated introns with reads": "2 of 3",
        "Intron with no read": "bases 1,381,746 to 1,382,305",
        "What the RNA-seq shows there": "junctions that join an exon the model lacks",
        "RNA-seq junctions that replace it": (
            "1,381,746 to 1,381,886 (1,436 reads; tracks: 1) and "
            "1,382,045 to 1,382,280 (1,686 reads; tracks: 1)"
        ),
        "Evidence not read": "None",
        "Corrected protein": "341 residues, frame kept",
        "Orthologs that match": (
            "8 for the corrected model, 0 for the annotated one, of 16 read"
        ),
    }


def test_each_intron_outcome_states_its_evidence() -> None:
    replaced = _introns(IntronConfirmation(result=AFU8_INTRONS))
    noncanonical = _introns(
        IntronConfirmation(result=intron_audit("UNSUPPORTED_NONCANONICAL"))
    )
    retained = _introns(IntronConfirmation(result=AGAP3685_INTRONS))
    assert (
        replaced["What the RNA-seq shows there"],
        replaced["RNA-seq junctions that replace it"],
        replaced["Corrected protein"],
        replaced["Orthologs that match"],
    ) == (
        "a junction that replaces it",
        "202,209 to 202,266 (18,608 reads; tracks: 1)",
        "93 residues, frame not kept",
        "0 for the corrected model, 8 for the annotated one, of 16 read",
    )
    assert (
        noncanonical["What the RNA-seq shows there"],
        noncanonical["Splice-site bases"],
        noncanonical["Why no correction"],
    ) == (
        "its splice-site bases are not canonical",
        "AT..AC",
        "the correction is not read",
    )
    assert (
        retained["What the RNA-seq shows there"],
        retained["Splice-site bases"],
        retained["Read depth"],
        retained["Evidence not read"],
    ) == (
        "reads cover it and none splices it",
        "GT..AG",
        (
            "median 4.17 against an exon median of 7.83 (53%; RETAINED needs 25% or "
            "more), 99% of its bases covered (RETAINED needs 90% or more), track "
            "E-MTAB-2880:E_20h_F (unique reverse)"
        ),
        "None",
    )


def test_an_intron_across_an_assembly_gap_reads_as_unread() -> None:
    facts = _introns(IntronConfirmation(result=AGAP7279_INTRONS))
    assert (
        facts["What the RNA-seq shows there"],
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


def test_relatives_and_gene_records_state_their_numbers() -> None:
    relatives = RelativesEvidence(
        reference_gene="REF",
        reference_length=319,
        model_length=110,
        relatives_median=300.0,
        side="STRAIN_SHORT",
        reference_organism="Plasmodium falciparum 3D7",
    )
    assert _pairs(relatives_facts(relatives)) == [
        ("Reference model", "REF in Plasmodium falciparum 3D7, 319 residues"),
        ("This model", "110 residues"),
        ("Median of independent related genomes", "300 residues"),
        (
            "Which model the related genomes support",
            "Related genomes match the reference, so the strain model is too short",
        ),
    ]
    records = GeneEvidencePayload(genes=(PIGA,), evidence=(PIGA_EVIDENCE,))
    assert _pairs(gene_evidence_facts(records)) == [
        ("PF3D7_1032400 citations", "2 PubMed articles, 0 comments, 0 notes"),
        (
            "PF3D7_1032400 structures",
            "4 PDB similarities; AlphaFold Q8IJ83 covers residues 1 to 461 of 461",
        ),
        ("PF3D7_1032400 peptides", "None served"),
    ]
    summary = evidence_summary([evidence_facts(relatives), evidence_facts(records)])
    assert summary.startswith(
        "Reference model: REF in Plasmodium falciparum 3D7, 319 residues; "
        "This model: 110 residues; "
    )
    assert summary.endswith("; PF3D7_1032400 peptides: None served")


def test_a_relatives_read_with_nothing_measured_reads_as_not_read() -> None:
    unmeasured = RelativesEvidence(
        reference_gene="REF",
        reference_length=None,
        model_length=None,
        relatives_median=None,
    )
    assert _pairs(relatives_facts(unmeasured)) == [
        ("Reference model", "REF, length not read"),
        ("This model", "Not read"),
        ("Median of independent related genomes", "Not read"),
        ("Which model the related genomes support", "Not judged"),
    ]
