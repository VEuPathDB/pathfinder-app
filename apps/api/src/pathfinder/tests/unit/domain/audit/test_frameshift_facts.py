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

_REFERENCE = ReferenceRun(
    gene="PF3D7_0407700",
    source=GenomeSource(site="plasmodb", organism="pfal3D7", seqid="Pf3D7_04_v3"),
    strand="-",
    start=359000,
    end=359027,
    bases=28,
)
_VARIANT = "Variant_Pf3D7_04_v3_359000"


def _calls(answer: VariantAnswer, bases: int | None = 28) -> VariantCalls:
    return VariantCalls(
        site="plasmodb",
        organism="Plasmodium falciparum 3D7",
        seqid="Pf3D7_04_v3",
        start=358999,
        end=359028,
        variants=[_VARIANT],
        sample="DD2_WTSI",
        calls=[
            StrainCall(
                variant=_VARIANT,
                genotype="1",
                allele="AA",
                depth="49",
                read_frequency="100.00",
            )
        ],
        answer=answer,
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
        "CM019789.1 bases 380,000 to 380,028 (minus strand), frame 1 to frame 2, one "
        "base more than the reference, at residues 529 to 538 of the reference protein"
    )
    assert _value(facts, "Run at the change") == (
        "29 bases of A, CM019789.1 380,000 to 380,028, from the plasmodb genome of pfalNF54"
    )
    assert _value(facts, "Same run in the reference strain") == "Not read"
    assert _value(facts, "Strain's reads at the run") == "Not read"


def test_a_frameshift_compares_the_run_with_the_reference_strain() -> None:
    shift = FRAMESHIFT.model_copy(update={"reference_run": _REFERENCE})

    assert _value(_facts(shift), "Same run in the reference strain") == (
        "28 bases in PF3D7_0407700, Pf3D7_04_v3 359,000 to 359,027, from the plasmodb "
        "genome of pfal3D7"
    )


def test_a_frameshift_with_no_run_says_so() -> None:
    shift = FRAMESHIFT.model_copy(update={"run": None})

    assert _value(_facts(shift), "Run at the change") == "None found"


def test_the_strains_calls_name_the_search_the_sample_and_the_variants() -> None:
    shift = FRAMESHIFT.model_copy(
        update={"reference_run": _REFERENCE, "variant_calls": _calls("INDEL_CALLED")}
    )

    assert _value(_facts(shift), "Strain's reads at the run") == (
        "The strain's reads carry an indel here, so the change is in the strain. "
        "plasmodb variation search VariantsByLocation, table VariantStrains, sample "
        f"DD2_WTSI, variants {_VARIANT}"
    )


def test_no_indel_outside_a_long_run_says_the_assembly_likely_miscounts() -> None:
    shift = FRAMESHIFT.model_copy(
        update={"variant_calls": _calls("NO_INDEL_CALLED", bases=None)}
    )

    assert _value(_facts(shift), "Strain's reads at the run").startswith(
        "The strain's reads carry no indel here, so the assembly likely miscounts the run."
    )


def test_a_missing_call_in_a_long_run_makes_no_claim_on_the_assembly() -> None:
    shift = FRAMESHIFT.model_copy(update={"variant_calls": _calls("NO_VARIANT_CALLED")})

    value = _value(_facts(shift), "Strain's reads at the run")

    assert value.startswith("The site's calls hold almost no indel in a run this long")
    assert "miscounts" not in value


def test_a_strain_frameshift_states_the_same_facts() -> None:
    facts = strain_facts(strain_frameshift(FRAMESHIFT))

    assert _value(facts, "The strain's DNA over the lost part") == (
        "The model follows the assembly, whose DNA holds the part the model lacks in "
        "another reading frame"
    )
    assert _value(facts, "Run at the change").startswith("29 bases of A")
