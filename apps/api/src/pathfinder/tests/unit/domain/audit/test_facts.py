from __future__ import annotations

from veupathdb_mcp.audit import PseudogeneCallAudit

from pathfinder.domain.audit.check_facts import confirmation_facts, evidence_facts
from pathfinder.domain.audit.confirmations import (
    MissingGeneConfirmation,
    OrganelleConfirmation,
    PseudogeneConfirmation,
    SelenoproteinConfirmation,
)
from pathfinder.domain.audit.facts import (
    Fact,
    evidence_summary,
    gene_evidence_facts,
    relatives_facts,
    runs_text,
)
from pathfinder.domain.audit.findings import GeneEvidencePayload, RelativesEvidence
from pathfinder.tests._support.audit import PIGA, PIGA_INTACT, SELK_STOPS, revised
from pathfinder.tests._support.audit_answers import missing, organelle
from pathfinder.tests._support.audit_evidence import (
    DMAW,
    GLO1,
    K13,
    PIGA_EVIDENCE,
    evidence_of,
)

UNREAD = "the strain region is unreadable"


def _pairs(facts: tuple[Fact, ...]) -> list[tuple[str, str]]:
    return [(fact.label, fact.value) for fact in facts]


def test_a_pseudogene_call_states_its_rebuilt_sequence() -> None:
    assert _pairs(confirmation_facts(PseudogeneConfirmation(result=PIGA_INTACT))) == [
        ("Reference coding sequence", "1,386 bases"),
        ("Strain sequence rebuilt through it", "1,386 bases"),
        ("Bases that match the reference", "1,386 of 1,386"),
        ("Stops inside the rebuilt protein", "None found"),
        ("Amino acids that differ from the reference", "0"),
    ]


def test_a_pseudogene_call_states_its_stops_and_the_evidence_it_did_not_read() -> None:
    stopped = revised(PIGA_INTACT, premature_stops=[12, 40], evidence_unread=[UNREAD])
    facts = _pairs(confirmation_facts(PseudogeneConfirmation(result=stopped)))
    assert (facts[3], facts[-1]) == (
        ("Stops inside the rebuilt protein", "at residues 12 and 40"),
        ("Evidence not read", UNREAD),
    )


def _stops(result: PseudogeneCallAudit) -> str:
    (stops,) = [
        fact.value
        for fact in confirmation_facts(PseudogeneConfirmation(result=result))
        if fact.label == "Stops inside the rebuilt protein"
    ]
    return stops


def test_a_cut_stop_list_says_how_many_it_lists() -> None:
    twenty = list(range(1, 21))
    listed = (
        "at residues 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19 "
        "and 20"
    )
    cut = revised(PIGA_INTACT, premature_stops=twenty, premature_stops_truncated=True)
    whole = revised(PIGA_INTACT, premature_stops=twenty)
    assert (_stops(cut), _stops(whole)) == (f"{listed} (the first 20)", listed)


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


def test_a_missing_gene_states_what_the_dna_holds() -> None:
    absent = confirmation_facts(
        MissingGeneConfirmation(result=missing("IN_DNA_UNANNOTATED"))
    )
    assert _pairs(absent) == [
        ("Gene looked for", "TGARI_257090, 359 residues"),
        ("Genome it is absent from", "Toxoplasma gondii GT1"),
        ("Conserved neighbours", "TGGT1_257070 and TGGT1_257100 on TGGT1_chrVIIb"),
        (
            "Where the DNA encodes it",
            "34 of 34 parts of the gene, bases 4,156,680 to 4,157,729",
        ),
        (
            "Open reading frame there",
            "196 residues, 196 identical to the gene looked for",
        ),
        ("Stops in the frame", "at residue 163"),
        ("The frame is whole", "No"),
        ("Models annotated there", "None found"),
        ("Members of its group annotated in the genome", "None found"),
        ("Genetic code", "Standard (inferred)"),
    ]


def test_a_missing_gene_names_the_models_and_members_it_found() -> None:
    other = dict(
        _pairs(
            confirmation_facts(
                MissingGeneConfirmation(result=missing("IN_DNA_OTHER_MODEL"))
            )
        )
    )
    annotated = dict(
        _pairs(
            confirmation_facts(
                MissingGeneConfirmation(result=missing("ANNOTATED_IN_GENOME"))
            )
        )
    )
    unanchored = dict(
        _pairs(
            confirmation_facts(MissingGeneConfirmation(result=missing("NO_SYNTENY")))
        )
    )
    assert other["Models annotated there"] == "TGGT1_257091 (conserved protein)"
    assert (
        annotated["Members of its group annotated in the genome"],
        annotated["Conserved neighbours"],
        annotated["Where the DNA encodes it"],
        annotated["Models annotated there"],
    ) == ("TGGT1_999999 on TGGT1_chrX", "Not read", "Not read", "Not read")
    assert unanchored["Conserved neighbours"] == "None found"


def test_a_selenoprotein_end_states_its_tail() -> None:
    unread = revised(
        SELK_STOPS,
        verdict="CONTAINS_SEC",
        tail_identity=None,
        sec_aligned=None,
        models=[None, None],
        evidence_unread=[UNREAD, UNREAD],
    )
    assert _pairs(confirmation_facts(SelenoproteinConfirmation(result=SELK_STOPS))) == [
        ("Residues the genome encodes after the model's end", "*G*"),
        ("The reference's last residues (U is selenocysteine)", "UG"),
        ("Identity of the two ends", "100%"),
        ("The model's stop sits where the reference has selenocysteine", "Yes"),
    ]
    assert _pairs(confirmation_facts(SelenoproteinConfirmation(result=unread)))[2:] == [
        ("Identity of the two ends", "Not read"),
        ("The model's stop sits where the reference has selenocysteine", "Not read"),
        ("Evidence not read", f"{UNREAD}; {UNREAD}"),
    ]


def test_runs_read_as_spans_joined_in_words() -> None:
    assert [runs_text(runs) for runs in ([], [(1, 9)], [(1, 9), (20, 1200)])] == [
        "None found",
        "1 to 9",
        "1 to 9 and 20 to 1,200",
    ]


def test_relatives_state_their_numbers() -> None:
    relatives = RelativesEvidence(
        reference_gene="REF",
        reference_length=319,
        model_length=110,
        relatives_median=300.0,
        side="STRAIN_SHORT",
        reference_organism="Plasmodium falciparum 3D7",
    )
    unmeasured = RelativesEvidence(
        reference_gene="REF",
        reference_length=None,
        model_length=None,
        relatives_median=None,
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
    assert _pairs(relatives_facts(unmeasured)) == [
        ("Reference model", "REF, length not read"),
        ("This model", "Not read"),
        ("Median of independent related genomes", "Not read"),
        ("Which model the related genomes support", "Not read"),
    ]


def test_stored_relative_lengths_state_their_count_and_range() -> None:
    relatives = RelativesEvidence(
        reference_gene="REF",
        reference_length=1319,
        model_length=110,
        relatives_median=1300.0,
        relative_lengths={"P. vivax": 1300, "P. knowlesi": 1302, "P. berghei": 1298},
    )
    assert _pairs(relatives_facts(relatives)) == [
        ("Reference model", "REF, 1,319 residues"),
        ("This model", "110 residues"),
        ("Median of independent related genomes", "1300 residues"),
        ("Related genomes read", "3 genomes, 1,298 to 1,302 residues"),
        ("Which model the related genomes support", "Not read"),
    ]


def test_gene_records_state_their_citations_structures_and_peptides() -> None:
    genes = (PIGA, K13, GLO1, DMAW)
    records = GeneEvidencePayload(
        genes=genes, evidence=(PIGA_EVIDENCE, *(evidence_of(g) for g in genes[1:]))
    )
    assert _pairs(gene_evidence_facts(records)) == [
        ("PF3D7_1032400 citations", "2 PubMed articles, 0 comments, 0 notes"),
        (
            "PF3D7_1032400 structures",
            "4 PDB similarities; AlphaFold Q8IJ83 covers residues 1 to 461 of 461",
        ),
        ("PF3D7_1032400 peptides", "None found"),
        ("PF3D7_1343700 citations", "44 PubMed articles, 9 comments, 2 notes"),
        (
            "PF3D7_1343700 structures",
            "13 PDB similarities; AlphaFold Q8IDQ2 covers residues 1 to 726 of 726",
        ),
        ("PF3D7_1343700 peptides", "59 peptides, 404 spectra"),
        ("LmjF.35.3010 citations", "2 PubMed articles, 0 comments, 1 note"),
        (
            "LmjF.35.3010 structures",
            "20 PDB similarities; AlphaFold Q68RJ8 covers residues 1 to 141 of 141",
        ),
        ("LmjF.35.3010 peptides", "8 peptides, 10 spectra"),
        ("Afu2g18040 citations", "24 PubMed articles, 1 comment, 10 notes"),
        ("Afu2g18040 structures", "5 PDB similarities; no AlphaFold model"),
        ("Afu2g18040 peptides", "None found"),
    ]


def test_the_summary_joins_every_fact_of_every_group() -> None:
    relatives = RelativesEvidence(
        reference_gene="REF",
        reference_length=319,
        model_length=110,
        relatives_median=None,
    )
    records = GeneEvidencePayload(genes=(PIGA,), evidence=(PIGA_EVIDENCE,))
    assert evidence_summary([evidence_facts(relatives), evidence_facts(records)]) == (
        "Reference model: REF, 319 residues; This model: 110 residues; "
        "Median of independent related genomes: Not read; "
        "Which model the related genomes support: Not read; "
        "PF3D7_1032400 citations: 2 PubMed articles, 0 comments, 0 notes; "
        "PF3D7_1032400 structures: 4 PDB similarities; AlphaFold Q8IJ83 covers "
        "residues 1 to 461 of 461; PF3D7_1032400 peptides: None found"
    )
