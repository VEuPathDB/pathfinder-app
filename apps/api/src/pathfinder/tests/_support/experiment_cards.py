"""Two other-site experiments as the cryptodb and toxodb dataset reports render them."""

from __future__ import annotations

from veupathdb_mcp.catalog import ExperimentCard, ExperimentMatch

CRYPTO_SEARCH = (
    "GenesByRNASeqcparIowaII_Isaza_Infection_Time_Series_ebi_rnaSeq_RSRCPercentile"
)

CRYPTO_CARD = ExperimentCard.model_validate(
    {
        "siteId": "cryptodb",
        "datasetId": "DS_63b0de882c",
        "name": "Transcriptome of 48 hours in vitro infection",
        "organism": "Cryptosporidium parvum Iowa II",
        "assay": "RNASeq",
        "attribution": "Isaza et al.",
        "summary": (
            "Transcriptome (RNA-Seq) from Cryptosporidium parvum Iowa isolated from "
            "an in vitro infection of cultured HCT-8 cells."
        ),
        "pmids": ["26549794"],
        "searches": ["GenesByIntronJunctions", CRYPTO_SEARCH],
        "recordUrl": "https://cryptodb.org/cryptodb/app/record/dataset/DS_63b0de882c",
    }
)

TOXO_CARD = ExperimentCard.model_validate(
    {
        "siteId": "toxodb",
        "datasetId": "DS_0d220fc0c6",
        "name": "Mouse brain bradyzoite transcriptomes at 28, 90, 120 days post infection",
        "organism": "Toxoplasma gondii ME49",
        "assay": "RNASeq",
        "attribution": "Garfoot et al.",
        "summary": (
            "Transcriptome of bradyzoites from mouse brain cysts via RNA-Seq at 28, "
            "90 and 120 days post-infection."
        ),
        "pmids": ["31726967"],
        "searches": [
            "GenesByRNASeqtgonME49_Knoll_Mouse_Brain_ebi_rnaSeq_RSRC",
            "GenesByIntronJunctions",
            "GenesByRNASeqtgonME49_Knoll_Mouse_Brain_ebi_rnaSeq_RSRCPercentile",
            "GenesByRNASeqtgonME49_Knoll_Mouse_Brain_ebi_rnaSeq_RSRCDESeq",
        ],
        "recordUrl": "https://toxodb.org/toxo/app/record/dataset/DS_0d220fc0c6",
    }
)

CRYPTO = ExperimentMatch(card=CRYPTO_CARD, similarity=0.5213)
TOXO = ExperimentMatch(card=TOXO_CARD, similarity=0.4107)

EIMERIA_GENOME_CARD = ExperimentCard.model_validate(
    {
        "siteId": "toxodb",
        "datasetId": "DS_299615a94a",
        "name": "Eimeria tenella strain Houghton Genome Sequence and Annotation",
        "organism": "Eimeria tenella strain Houghton",
        "assay": "Genomes",
        "attribution": "Adam J. Reid",
        "summary": "Eimeria tenella Houghton sequence and annotation",
        "pmids": ["25015382"],
        "searches": [
            "GenesByInterproDomain",
            "GenesWithSignalPeptide",
            "GeneByLocusTag",
            "GenesByTransmembraneDomains",
            "GenesWithUserComments",
            "GenesByExonCount",
            "GenesByTaxon",
            "GenesByGeneModelChars",
            "GenesByLocation",
        ],
        "recordUrl": "https://toxodb.org/toxo/app/record/dataset/DS_299615a94a",
    }
)

LEISHMANIA_ISOLATES_CARD = ExperimentCard.model_validate(
    {
        "siteId": "tritrypdb",
        "datasetId": "DS_2184f85560",
        "name": "Aligned genomic sequence reads - 16 clinical isolates",
        "organism": "Leishmania donovani BPK282A1",
        "assay": "isolates",
        "attribution": "Matthew Berriman",
        "summary": (
            "Whole genome resequencing data from 16 clinical isolates of Leishmania "
            "donovani were used to call SNPs and determine CNV at the gene and "
            "chromosome level."
        ),
        "pmids": ["22038251"],
        "searches": [
            "GenesByNgsSnps",
            "GenesByCopyNumberComparison",
            "GenesByVariantCharacteristics",
            "GenesByCopyNumber",
        ],
        "recordUrl": "https://tritrypdb.org/tritrypdb/app/record/dataset/DS_2184f85560",
    }
)
