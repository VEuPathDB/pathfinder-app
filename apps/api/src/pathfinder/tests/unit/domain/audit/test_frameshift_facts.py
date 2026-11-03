from __future__ import annotations

from veupathdb_mcp.audit import (
    Frameshift,
    GenomeSource,
    ReferenceRun,
    StrainCall,
    VariantAnswer,
    VariantCalls,
)

from pathfinder.domain.audit.facts import Fact
from pathfinder.domain.audit.length_facts import length_facts, strain_facts
from pathfinder.tests._support.audit import FRAMESHIFT, revised, short_audit
from pathfinder.tests._support.audit_answers import strain_frameshift

_VARIANT = "constructed_variant"
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


def _calls(
    answer: VariantAnswer,
    bases: int | None = 28,
    effects: dict[str, str | None] | None = None,
) -> VariantCalls:
    effects = {_VARIANT: None} if effects is None else effects
    return VariantCalls(
        site="constructed_site",
        organism="constructed organism",
        seqid="constructed_ref_seq",
        start=358999,
        end=359028,
        variants=[_VARIANT],
        samples=["CONSTRUCTED_SAMPLE"],
        calls=[
            StrainCall(
                sample="CONSTRUCTED_SAMPLE",
                variant=_VARIANT,
                genotype="1",
                allele="G",
                depth="49",
                read_frequency="100.00",
            )
        ],
        answer=answer,
        sample_answers={"CONSTRUCTED_SAMPLE": answer},
        frame_effects=effects,
        homopolymer_bases=bases,
    )


def _facts(shift: Frameshift) -> tuple[Fact, ...]:
    audit = short_audit("G1", reference_gene="R1", verdict="FRAMESHIFT")
    return length_facts(revised(audit, frameshifts=[shift]))


def _value(facts: tuple[Fact, ...], label: str) -> str:
    return next(fact.value for fact in facts if fact.label == label)


def test_a_frameshift_names_its_place_frames_and_run_with_their_source() -> None:
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
    assert _value(facts, "Same run in the reference strain") == (
        "No reference strain was compared"
    )
    assert _value(facts, "Strain's reads at the run") == "Not read"


def test_a_frameshift_never_counts_bases_against_the_reference_protein() -> None:
    assert "more than the reference" not in _value(_facts(FRAMESHIFT), "Frame change")


def test_a_frameshift_compares_the_run_with_the_reference_strain() -> None:
    shift = FRAMESHIFT.model_copy(update={"reference_run": _REFERENCE})

    assert _value(_facts(shift), "Same run in the reference strain") == (
        "28 bases in constructed_reference, constructed_ref_seq 359,000 to 359,027, from "
        "the constructed_site genome of constructed_ref"
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
    assert _value(facts, "Strain's reads at the run") == (
        "Not read, because the run was not placed in the reference"
    )


def test_a_frameshift_with_no_run_says_so() -> None:
    shift = FRAMESHIFT.model_copy(update={"run": None})

    assert _value(_facts(shift), "Run at the change") == "None found"


def test_the_strains_calls_name_the_search_the_range_and_the_variants() -> None:
    shift = FRAMESHIFT.model_copy(
        update={
            "reference_run": _REFERENCE,
            "variant_calls": _calls("ALTERNATE_AT_INDEL_SITE"),
        }
    )

    value = _value(_facts(shift), "Strain's reads at the run")

    assert value == (
        "The strain's reads differ from the reference at an indel the site does not "
        "call in frame. It is not established that this is the change. "
        "constructed_site variation search VariantsByLocation for constructed organism "
        "over constructed_ref_seq 358,999 to 359,028, table VariantStrains, samples "
        f"CONSTRUCTED_SAMPLE, variants {_VARIANT}, indel_frame_effect {_VARIANT}: not "
        "served"
    )
    assert "change is in the strain" not in value


def test_an_in_frame_indel_names_the_attribute_that_says_so() -> None:
    shift = FRAMESHIFT.model_copy(
        update={
            "variant_calls": _calls(
                "IN_FRAME_INDEL_CALLED",
                bases=None,
                effects={_VARIANT: "inframe_deletion"},
            )
        }
    )

    value = _value(_facts(shift), "Strain's reads at the run")

    assert value.startswith(
        "The strain's reads carry an indel here that the site calls in frame, which "
        "cannot be the change that shifted the frame."
    )
    assert value.endswith(f"indel_frame_effect {_VARIANT}: inframe_deletion")


def test_another_frame_effect_value_is_stated_as_served() -> None:
    shift = FRAMESHIFT.model_copy(
        update={
            "variant_calls": _calls(
                "ALTERNATE_AT_INDEL_SITE",
                bases=None,
                effects={_VARIANT: "constructed_effect"},
            )
        }
    )

    value = _value(_facts(shift), "Strain's reads at the run")

    assert "It is not established" in value
    assert value.endswith(f"indel_frame_effect {_VARIANT}: constructed_effect")


def test_an_in_frame_indel_supports_the_miscount_as_no_indel_does() -> None:
    shift = FRAMESHIFT.model_copy(
        update={
            "reference_run": _REFERENCE,
            "variant_calls": _calls(
                "IN_FRAME_INDEL_CALLED",
                bases=None,
                effects={_VARIANT: "inframe_deletion"},
            ),
        }
    )

    assert "The assembly likely miscounts the run." in _reads(shift)


def _reads(shift: Frameshift) -> str:
    return _value(_facts(shift), "Strain's reads at the run")


def test_a_miscount_is_said_only_when_all_the_evidence_shows_it() -> None:
    shift = FRAMESHIFT.model_copy(
        update={
            "reference_run": _REFERENCE,
            "variant_calls": _calls("NO_INDEL_CALLED", bases=None),
        }
    )

    assert _reads(shift).startswith(
        "The strain's reads are called as the reference at this place. "
        "The assembly likely miscounts the run."
    )


def test_equal_counts_are_stated_as_evidence_against_a_miscount() -> None:
    run = FRAMESHIFT.run
    assert run is not None
    shift = FRAMESHIFT.model_copy(
        update={
            "run": run.model_copy(update={"bases": 28}),
            "reference_run": _REFERENCE,
            "variant_calls": _calls("NO_INDEL_CALLED", bases=None),
        }
    )

    value = _reads(shift)

    assert "The run holds as many bases in both strains" in value
    assert "miscounts" not in value


def test_a_missing_call_in_a_long_run_makes_no_claim_on_the_assembly() -> None:
    shift = FRAMESHIFT.model_copy(
        update={
            "reference_run": _REFERENCE,
            "variant_calls": _calls("NO_INDEL_CALLED"),
        }
    )

    value = _reads(shift)

    assert value.startswith("The site's calls hold almost no indel in a run this long")
    assert "miscounts" not in value


def test_no_variant_in_any_sample_makes_no_claim_on_the_assembly() -> None:
    shift = FRAMESHIFT.model_copy(
        update={
            "reference_run": _REFERENCE,
            "variant_calls": _calls("NO_VARIANT_CALLED", bases=None),
        }
    )

    value = _reads(shift)

    assert value.startswith("No sample has a variant here")
    assert "miscounts" not in value


def test_no_matched_sample_does_not_say_the_strain_was_not_sequenced() -> None:
    shift = FRAMESHIFT.model_copy(
        update={
            "reference_run": _REFERENCE,
            "variant_calls": _calls("NO_SAMPLE_MATCHED", bases=None),
        }
    )

    value = _reads(shift)

    assert value.startswith("No sample of the site's calls was matched to the strain")
    assert "sequenced" not in value


def test_a_strain_frameshift_states_the_same_facts() -> None:
    facts = strain_facts(strain_frameshift(FRAMESHIFT))

    assert _value(facts, "The strain's DNA over the lost part") == (
        "The model follows the genome sequence, whose DNA holds the part the model lacks "
        "in another reading frame"
    )
    assert _value(facts, "Run at the change").startswith("29 bases of A")
    assert _value(facts, "Reference protein").startswith("constructed_reference_gene")
