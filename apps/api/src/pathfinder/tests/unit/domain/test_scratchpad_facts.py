"""The identifiers a note carries, read by shape from its text."""

from __future__ import annotations

from pathfinder.domain.scratchpad_facts import hard_facts

_UNION_NOTE = """\
Verified P. falciparum signal peptide or transmembrane strategy
Completed UNION strategy returned 1,203 Plasmodium falciparum 3D7 records; leaf \
counts were 479 signal-peptide and 840 transmembrane records, with sampled records \
and controls supporting the result.
Root step_45c4d00d is a UNION of step_ec8f848b (GenesWithSignalPeptide, organism \
Plasmodium falciparum 3D7, SignalP-6.0; 479 records) and step_d284e9c9 \
(GenesByTransmembraneDomains, organism Plasmodium falciparum 3D7, min_tm=2, \
max_tm=99; 840 records). Root count: 1,203. Verification sampled 8 records, all \
consistent with either non-null SignalP-6.0 probability or tm_count in the \
requested range. Controls: PF3D7_0100600 and PF3D7_0101300 positive; \
PF3D7_1246200 and PF3D7_API01700 negative."""

_WDK_STEPS_NOTE = """\
Verification: signal peptide and >=1 TM and sporozoite expression
Built strategy returned 55 P. falciparum 3D7 transcripts meeting signal peptide, \
>=1 TM, and sporozoite RNA-seq percentile >=80.
WDK strategy 330426063 (root step 439856393) verified.
Per-step summary:
- GenesWithSignalPeptide (wdk_step_id=439856353): estimated_size=603; \
organism=Plasmodium falciparum 3D7
- GenesByTransmembraneDomains (wdk_step_id=439856363): estimated_size=1628; \
min_tm=1, max_tm=99
- INTERSECT(SP,TM) (wdk_step_id=439856373): estimated_size=324
- GenesByRNASeq...Sporozoite (wdk_step_id=439856383): estimated_size=1076; \
min_expression_percentile=80, max_expression_percentile=100, samples=['Sporozoite']
- Final INTERSECT (wdk_step_id=439856393): estimated_size=55
Notes: sample records inspected; no zero or huge steps; control tests not run \
(no control gene IDs provided)."""


def test_a_union_note_carries_its_genes_steps_searches_and_counts() -> None:
    assert hard_facts(_UNION_NOTE) == frozenset(
        {
            "PF3D7_0100600",
            "PF3D7_0101300",
            "PF3D7_1246200",
            "PF3D7_API01700",
            "step_45c4d00d",
            "step_ec8f848b",
            "step_d284e9c9",
            "GenesWithSignalPeptide",
            "GenesByTransmembraneDomains",
            "1203",
            "479",
            "840",
        }
    )


def test_a_wdk_step_summary_carries_every_step_id_and_estimate() -> None:
    assert hard_facts(_WDK_STEPS_NOTE) == frozenset(
        {
            "330426063",
            "439856393",
            "439856353",
            "439856363",
            "439856373",
            "439856383",
            "603",
            "1628",
            "324",
            "1076",
            "100",
            "GenesWithSignalPeptide",
            "GenesByTransmembraneDomains",
            "GenesByRNASeq",
        }
    )


def test_gene_ids_of_each_site_shape_are_facts() -> None:
    text = "TGME49_233460, Tb927.10.1000, AAEL000001, C4_01920W_A and cgd7_2270."

    assert hard_facts(text) == frozenset(
        {"TGME49_233460", "Tb927.10.1000", "AAEL000001", "C4_01920W_A", "cgd7_2270"}
    )


def test_a_count_with_a_thousands_separator_is_the_same_fact_without_it() -> None:
    assert hard_facts("the union has 20,846 genes") == hard_facts("20846 genes")
    assert hard_facts("20846 genes") == frozenset({"20846"})


def test_accessions_decimals_note_ids_and_short_numbers_are_not_facts() -> None:
    text = (
        "GO:0016301, PF00069, p 0.001, ratio 1234.5, [n-123456], 3D7, 16 steps, 2026-09"
    )

    assert hard_facts(text) == frozenset({"2026"})


def test_a_search_name_is_the_whole_url_segment() -> None:
    name = "GenesByRNASeqaaegLVP_AGWG_SRP115939_ebi_rnaSeq_RSRCDESeq"

    assert hard_facts(f"ran {name} at fold 2") == frozenset({name})
