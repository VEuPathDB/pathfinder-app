from __future__ import annotations

from pathlib import Path

import pytest
from veupathdb_mcp.audit import (
    FrameChange,
    GenomeSource,
    ReferenceRun,
    SplicePair,
    StrainCall,
    VariantCalls,
    VariantSite,
)

from pathfinder.domain.audit import length_facts as facts_module
from pathfinder.domain.audit.facts import Fact
from pathfinder.domain.audit.length_facts import length_facts, strain_facts
from pathfinder.tests._support.audit import FRAMESHIFT, revised, short_audit
from pathfinder.tests._support.audit_answers import strain_frameshift

_PAIR = SplicePair(motif="GT..AG", donor=10, acceptor=40)
_RECORD = "constructed_variant"
_REFERENCE = ReferenceRun(
    gene="constructed_reference",
    source=GenomeSource(
        site="constructed_site", organism="constructed_ref", seqid="constructed_ref_seq"
    ),
    strand="-",
    start=359000,
    end=359027,
    bases=28,
)
_INDEL_SITE = VariantSite(
    variant=_RECORD,
    variant_type="MIXED",
    indel_ref_allele="GAGGAAA",
    indel_frame_effect="inframe_deletion",
    calls=[
        StrainCall(
            sample="CONSTRUCTED_SAMPLE",
            genotype="1",
            allele="A",
            depth="49",
            read_frequency="100.00",
        )
    ],
)
_SNV_SITE = VariantSite(
    variant=_RECORD,
    variant_type="SNV",
    indel_ref_allele=None,
    indel_frame_effect=None,
    calls=[
        StrainCall(
            sample="CONSTRUCTED_SAMPLE",
            genotype="0",
            allele="G",
            depth="49",
            read_frequency="100.00",
        )
    ],
)
_HEADER = (
    "constructed_site variation search VariantsByLocation for constructed organism "
    "over constructed_ref_seq 358,999 to 359,028, table VariantStrains"
)


def _calls(
    sites: list[VariantSite],
    *,
    samples: list[str] | None = None,
    bases: int | None = 28,
) -> VariantCalls:
    return VariantCalls(
        site="constructed_site",
        organism="constructed organism",
        seqid="constructed_ref_seq",
        start=358999,
        end=359028,
        sites=sites,
        samples=["CONSTRUCTED_SAMPLE"] if samples is None else samples,
        homopolymer_bases=bases,
    )


def _facts(shift: FrameChange) -> tuple[Fact, ...]:
    audit = short_audit("G1", reference_gene="R1", verdict="FRAMESHIFT")
    return length_facts(revised(audit, frame_changes=[shift]))


def _value(facts: tuple[Fact, ...], label: str) -> str:
    return next(fact.value for fact in facts if fact.label == label)


def _reads(shift: FrameChange) -> str:
    return _value(_facts(shift), "Strain's reads at the run")


def test_a_change_names_its_place_frames_and_run_with_their_source() -> None:
    facts = _facts(FRAMESHIFT)

    assert _value(facts, "Frame change") == (
        "constructed_site genome constructed_genome, constructed_seq bases 380,000 to "
        "380,028 (minus strand), frame 1 to frame 2, a shift of +1 base against the "
        "reference protein's spacing"
    )
    assert _value(facts, "Reference protein") == "R1, residues 529 to 538"
    assert _value(facts, "Run at the change") == (
        "29 bases of A, constructed_seq 380,000 to 380,028, from the constructed_site "
        "genome of constructed_genome"
    )
    assert _value(facts, "Splice pair at the change") == "None found"
    assert _value(facts, "Same run in the reference strain") == (
        "No reference strain was compared"
    )
    assert _value(facts, "Run counts") == "Not compared"
    assert _reads(FRAMESHIFT) == "Not read"


def test_what_the_model_holds_past_a_change_is_stated_and_no_stop_is_claimed() -> None:
    goes_on = FRAMESHIFT.model_copy(update={"model_goes_on": True})

    assert _value(_facts(FRAMESHIFT), "Model past the change") == (
        "The model holds nothing past this change"
    )
    assert _value(_facts(goes_on), "Model past the change") == (
        "The model goes on past this change"
    )


def test_a_splice_pair_at_the_change_is_named_so_a_missed_exon_shows() -> None:
    shift = FRAMESHIFT.model_copy(
        update={"splice_pair": SplicePair(motif="GT..AG", donor=1200, acceptor=1233)}
    )

    assert _value(_facts(shift), "Splice pair at the change") == (
        "GT..AG, bases 1,200 to 1,233 of constructed_seq"
    )


@pytest.mark.parametrize(
    ("shift", "pair", "words"),
    [
        (3, None, "The reading frame holds"),
        (108, _PAIR, "The part lies across a splice pair in the same frame"),
        (1, None, "The reading frame changes"),
        (116, _PAIR, "The reading frame changes"),
    ],
)
def test_a_jump_states_what_it_does_to_the_frame(
    shift: int, pair: SplicePair | None, words: str
) -> None:
    change = FRAMESHIFT.model_copy(update={"shift": shift, "splice_pair": pair})

    assert _value(_facts(change), "Reading frame at the change") == words


def test_jumps_past_the_cap_are_stated_and_named_unread() -> None:
    audit = short_audit("G1", reference_gene="R1", verdict="FRAMESHIFT")
    paired = FRAMESHIFT.model_copy(update={"shift": 98, "splice_pair": _PAIR})
    bare = FRAMESHIFT.model_copy(update={"shift": -60})

    facts = length_facts(
        revised(audit, frame_changes=[FRAMESHIFT], unlisted_changes=[paired, bare])
    )

    assert _value(facts, "Changes past those listed, not read further") == (
        "2: a shift of +98 at GT..AG, a shift of -60 at no splice pair"
    )


def test_no_jump_past_the_cap_states_nothing() -> None:
    labels = [fact.label for fact in _facts(FRAMESHIFT)]

    assert "Changes past those listed, not read further" not in labels


def test_every_change_is_stated() -> None:
    other = FRAMESHIFT.model_copy(update={"shift": 2})
    audit = short_audit("G1", reference_gene="R1", verdict="FRAMESHIFT")

    facts = length_facts(revised(audit, frame_changes=[FRAMESHIFT, other]))

    assert [f.value for f in facts if f.label == "Frame change"][1].endswith(
        "a shift of +2 bases against the reference protein's spacing"
    )


def test_counts_that_differ_by_the_shift_are_stated_as_matching() -> None:
    shift = FRAMESHIFT.model_copy(update={"reference_run": _REFERENCE})

    facts = _facts(shift)

    assert _value(facts, "Same run in the reference strain") == (
        "28 bases in constructed_reference, constructed_ref_seq 359,000 to 359,027, from "
        "the constructed_site genome of constructed_ref"
    )
    assert _value(facts, "Run counts") == (
        "29 here against 28 in the reference strain, a difference of 1, which matches "
        "the shift of +1"
    )


def test_counts_that_do_not_differ_by_the_shift_read_as_a_mismatch() -> None:
    run = FRAMESHIFT.run
    assert run is not None
    shift = FRAMESHIFT.model_copy(
        update={
            "run": run.model_copy(update={"bases": 82}),
            "reference_run": _REFERENCE.model_copy(update={"bases": 8}),
        }
    )

    assert _value(_facts(shift), "Run counts") == (
        "82 here against 8 in the reference strain, a difference of 74, which does not "
        "match the shift of +1"
    )


def test_a_reference_that_was_read_says_why_the_run_was_not_placed() -> None:
    shift = FRAMESHIFT.model_copy(
        update={
            "reference_unread": "FLANK_REPEATED",
            "variants_unread": "NO_REFERENCE_RUN",
        }
    )
    facts = _facts(shift)

    assert _value(facts, "Same run in the reference strain") == (
        "The bases beside the run repeat in the reference gene, so the run cannot be "
        "placed"
    )
    assert _reads(shift) == "Not read, because the run was not placed in the reference"


def test_a_change_with_no_run_says_so() -> None:
    shift = FRAMESHIFT.model_copy(update={"run": None})

    assert _value(_facts(shift), "Run at the change") == "None found"


def test_each_record_is_stated_as_served_with_its_source() -> None:
    shift = FRAMESHIFT.model_copy(
        update={"variant_calls": _calls([_INDEL_SITE], bases=None)}
    )

    assert _reads(shift) == (
        f"{_HEADER}. {_RECORD}: variant_type MIXED, indel_ref_allele GAGGAAA, "
        "indel_frame_effect inframe_deletion; CONSTRUCTED_SAMPLE genotype 1, allele A, "
        "depth 49, read frequency 100.00"
    )


def test_a_snv_record_states_its_call_and_nothing_about_indels() -> None:
    shift = FRAMESHIFT.model_copy(
        update={"variant_calls": _calls([_SNV_SITE], bases=None)}
    )

    assert _reads(shift) == (
        f"{_HEADER}. {_RECORD}: variant_type SNV, indel_ref_allele not served, "
        "indel_frame_effect not served; CONSTRUCTED_SAMPLE genotype 0, allele G, "
        "depth 49, read frequency 100.00"
    )


def test_no_record_is_stated() -> None:
    shift = FRAMESHIFT.model_copy(update={"variant_calls": _calls([], bases=None)})

    assert _reads(shift) == f"{_HEADER}. The search holds no variant record here"


def test_a_long_run_with_no_indel_record_says_the_calls_say_little() -> None:
    shift = FRAMESHIFT.model_copy(update={"variant_calls": _calls([], bases=28)})

    assert _reads(shift).endswith(
        "The site's calls hold almost no indel in a run this long, so they say little "
        "here"
    )


def test_no_matched_sample_is_stated_beside_the_records() -> None:
    shift = FRAMESHIFT.model_copy(
        update={
            "variant_calls": _calls(
                [_INDEL_SITE.model_copy(update={"calls": []})], samples=[], bases=None
            )
        }
    )

    assert _reads(shift) == (
        f"{_HEADER}. {_RECORD}: variant_type MIXED, indel_ref_allele GAGGAAA, "
        "indel_frame_effect inframe_deletion. No sample of the site's calls was matched "
        "to the strain"
    )


def test_no_fact_concludes_a_cause() -> None:
    source = Path(str(facts_module.__file__)).read_text(encoding="utf-8")
    claims = (
        "miscount",
        "cannot be the change",
        "called as the reference",
        "in the strain",
    )

    assert [claim for claim in claims if claim in source] == []


def test_a_strain_frame_change_states_the_same_facts() -> None:
    facts = strain_facts(strain_frameshift(FRAMESHIFT))

    assert _value(facts, "The strain's DNA over the lost part") == (
        "The model follows the genome sequence, whose DNA holds the part the model lacks "
        "in another reading frame"
    )
    assert _value(facts, "Run at the change").startswith("29 bases of A")
    assert _value(facts, "Reference protein").startswith("constructed_reference_gene")
