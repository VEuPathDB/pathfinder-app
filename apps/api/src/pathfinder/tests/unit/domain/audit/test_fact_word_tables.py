from __future__ import annotations

from veupathdb_mcp.audit import GeneticCode

from pathfinder.domain.audit.facts import _CODES, TIER_WORDS, YES_NO
from pathfinder.domain.audit.intron_facts import _ACROSS_GAP, _OUTCOMES
from pathfinder.domain.audit.length_facts import (
    _EQUAL_COUNTS,
    _MISCOUNT,
    _NO_RELATIVES,
    _NOT_READ,
    _PARTS,
    _REFERENCE_MISSES,
    _UNDETERMINED,
    _VARIANT_ANSWERS,
    _VARIANTS_UNREAD,
)


def test_the_codes_table_reads_its_exact_words() -> None:
    assert _CODES == {
        GeneticCode.STANDARD: "Standard",
        GeneticCode.CTG_SERINE: "CTG read as serine",
        GeneticCode.UGA_TRYPTOPHAN: "UGA read as tryptophan",
        GeneticCode.YEAST_MITOCHONDRIAL: "Yeast mitochondrial",
        GeneticCode.INVERTEBRATE_MITOCHONDRIAL: "Invertebrate mitochondrial",
    }


def test_the_yes_no_table_reads_its_exact_words() -> None:
    assert YES_NO == {
        True: "Yes",
        False: "No",
        None: "Not read",
    }


def test_the_parts_table_reads_its_exact_words() -> None:
    assert _PARTS == {
        "model": "in the model",
        "genome_same_strand": "encoded on the same strand outside the model",
        "genome_other_strand": "encoded on the other strand",
        "absent": "not encoded",
        "weak": "matched weakly",
        "part1": "in the first model",
        "part2": "in the second model",
    }


def test_the_variant_answers_table_reads_its_exact_words() -> None:
    assert _VARIANT_ANSWERS == {
        "ALTERNATE_AT_INDEL_SITE": "The strain's reads differ from the reference at a site the calls mark as an indel. The table does not give the indel's length, so this does not show it is this change",
        "NO_INDEL_CALLED": "The strain's reads are called as the reference at this place",
        "NO_VARIANT_CALLED": "No sample has a variant here, and this does not show the strain was sequenced",
        "NOT_COVERED": "The strain's reads do not cover the indel site",
        "NO_SAMPLE_MATCHED": "No sample of the site's calls was matched to the strain",
        "CALL_UNREADABLE": "The strain's call here cannot be read as an indel or as none",
        "SAMPLES_DISAGREE": "The samples matched to the strain do not agree",
    }
    assert _UNDETERMINED == (
        "The site's calls hold almost no indel in a run this long, so a missing call "
        "does not show whether the strain's reads carry the change"
    )
    assert _MISCOUNT == "The assembly likely miscounts the run"
    assert _EQUAL_COUNTS == (
        "The run holds as many bases in both strains, which is evidence against a "
        "miscount"
    )
    assert _REFERENCE_MISSES == {
        "MODEL_UNREAD": "The reference gene's model could not be read",
        "WINDOW_TOO_LONG": "The reference gene spans more than an audit reads",
        "FLANK_SHORT": "The bases beside the run are too few to place it in the reference",
        "FLANK_MISSING": "The reference gene lacks the bases beside the run",
        "FLANK_REPEATED": "The bases beside the run repeat in the reference gene, so the run cannot be placed",
        "EMPTY_SPAN": "The reference gene holds nothing between the bases beside the run",
    }
    assert _VARIANTS_UNREAD == {
        "NO_REFERENCE_RUN": "Not read, because the run was not placed in the reference",
        "NO_VARIANT_SEARCH": "The site serves no variant search",
        "SEARCH_REFUSED": "The site refused the variant search for this organism, so the calls are unread",
        "TOO_MANY_VARIANTS": "More variants lie here than an audit reads, so the finding stands on the DNA alone",
    }


def test_the_tiers_table_reads_its_exact_words() -> None:
    assert TIER_WORDS == {
        "SAME_GENUS": "The same genus",
        "OTHER_GENERA": "Other genera",
    }


def test_the_no_relatives_table_reads_its_exact_words() -> None:
    assert _NO_RELATIVES == {
        "RESIDUAL_GROUP": "the ortholog group is a residual group",
        "PARALOGS": "the related genomes do not hold one copy each",
        "FEWER_THAN_TWO": "fewer than two independent related genomes hold the gene",
    }


def test_the_not_read_table_reads_its_exact_words() -> None:
    assert _NOT_READ == {
        "NO_LOST_RUN": "The strain protein lacks no run of the reference protein",
        "UNQUALIFIED": "The ortholog group is a residual group",
        "PARALOG_IN_WINDOW": "A paralog lies in the region the check reads",
    }


def test_the_outcomes_table_reads_its_exact_words() -> None:
    assert _OUTCOMES == {
        "SHIFTED": "an RNA-seq junction a few bases away",
        "MISSING_EXON": "RNA-seq junctions that join an exon the model lacks",
        "REPLACED": "an RNA-seq junction that replaces it",
        "NONCANONICAL": "the genome's splice-site bases are not canonical",
        "RETAINED": "RNA-seq reads cover it and none splices it",
        "UNEXPLAINED": "no evidence explains it",
    }


def test_the_assembly_gap_words_read_exactly() -> None:
    assert (
        _ACROSS_GAP
        == "it spans an assembly gap, so its splice-site bases were not read"
    )
