"""What an audit scope admits: explicit genomes or gene targets, never a whole site."""

from __future__ import annotations

from typing import get_args

import pytest
from pydantic import TypeAdapter, ValidationError

from pathfinder.domain.audit.scope import (
    DEFAULT_CONFIRM_LIMIT,
    MAX_UNNAMED_GENOME_TARGETS,
    AuditScope,
    CheckName,
    GenePairTarget,
    GeneTarget,
    MissingGeneTarget,
    OrganelleTarget,
    SingleGeneTarget,
    whole_genome_reads,
)

NF54 = "Plasmodium falciparum NF54"
GT1 = "Toxoplasma gondii GT1"
RELATIVES = tuple(f"Plasmodium relative{k} X" for k in range(9))
PIGA_PAIR = GenePairTarget(
    check="pseudogene_call", genes=("PfNF54_100037200", "PF3D7_1032400")
)
_TARGET: TypeAdapter[GeneTarget] = TypeAdapter(GeneTarget)
CAP = 8


def _admitted(**fields: object) -> AuditScope:
    return AuditScope.admitted(fields, max_genomes=CAP)


def test_every_check_has_a_target_shape() -> None:
    shapes = (SingleGeneTarget, GenePairTarget, MissingGeneTarget, OrganelleTarget)
    shaped = [
        check
        for shape in shapes
        for check in get_args(shape.model_fields["check"].annotation)
    ]
    assert sorted(shaped) == sorted(get_args(CheckName))


def test_a_missing_gene_target_names_the_organism_that_lacks_it() -> None:
    target = _TARGET.validate_python(
        {"check": "missing_gene", "genes": ["TGARI_257090"], "absentOrganism": GT1}
    )
    assert target == MissingGeneTarget(
        check="missing_gene", genes=("TGARI_257090",), absent_organism=GT1
    )
    assert target.key == "missing_gene:TGARI_257090:Toxoplasma gondii GT1"
    assert target.genome == GT1
    with pytest.raises(ValidationError, match="absentOrganism"):
        _TARGET.validate_python({"check": "missing_gene", "genes": ["TGARI_257090"]})


def test_an_organelle_target_names_its_contig() -> None:
    target = _TARGET.validate_python(
        {
            "check": "organelle_join",
            "genes": ["PF3D7_MIT02300"],
            "organism": NF54,
            "sequenceId": "CM019798.1",
        }
    )
    assert target.key == (
        "organelle_join:PF3D7_MIT02300:Plasmodium falciparum NF54:CM019798.1"
    )
    assert target.genome == NF54
    with pytest.raises(ValidationError, match="sequenceId"):
        _TARGET.validate_python(
            {"check": "organelle_join", "genes": ["PF3D7_MIT02300"], "organism": NF54}
        )


def test_a_fusion_target_names_one_gene_and_a_strain_target_two_in_order() -> None:
    fusion = _TARGET.validate_python({"check": "gene_fusion", "genes": ["AK88_02763"]})
    strain = _TARGET.validate_python(
        {"check": "strain_model", "genes": ["PcyM_0736700", "PCYB_074210"]}
    )
    assert (fusion.key, fusion.genome) == ("gene_fusion:AK88_02763", None)
    assert strain.genes == ("PcyM_0736700", "PCYB_074210")
    assert (strain.key, strain.genome) == (
        "strain_model:PcyM_0736700+PCYB_074210",
        None,
    )
    with pytest.raises(ValidationError):
        _TARGET.validate_python({"check": "gene_fusion", "genes": ["A", "B"]})


def test_a_target_reads_its_wire_form_by_its_check() -> None:
    target = _TARGET.validate_python(
        {"check": "gene_length", "genes": ["PcyM_0736700"]}
    )
    assert target == SingleGeneTarget(check="gene_length", genes=("PcyM_0736700",))
    assert target.key == "gene_length:PcyM_0736700"


def test_a_pair_check_names_two_genes() -> None:
    with pytest.raises(ValidationError):
        _TARGET.validate_python(
            {"check": "pseudogene_call", "genes": ["PfNF54_100037200"]}
        )
    assert PIGA_PAIR.key == "pseudogene_call:PfNF54_100037200+PF3D7_1032400"


def test_a_pair_never_names_one_gene_twice() -> None:
    with pytest.raises(ValidationError, match="gene_split names PF3D7_1032400 twice"):
        GenePairTarget(check="gene_split", genes=("PF3D7_1032400", "PF3D7_1032400"))


def test_a_split_pair_is_one_key_in_either_order() -> None:
    forward = GenePairTarget(check="gene_split", genes=("NF54_A", "NF54_B"))
    backward = GenePairTarget(check="gene_split", genes=("NF54_B", "NF54_A"))
    assert backward.genes == ("NF54_A", "NF54_B")
    assert backward.key == forward.key == "gene_split:NF54_A+NF54_B"
    with pytest.raises(ValidationError, match="is named twice"):
        AuditScope(site_id="plasmodb", targets=(forward, backward))


def test_a_strain_and_reference_pair_keeps_its_order() -> None:
    sec = GenePairTarget(
        check="selenoprotein_end", genes=("TGME49_316600", "TGGT1_316600")
    )
    assert sec.genes == ("TGME49_316600", "TGGT1_316600")
    assert PIGA_PAIR.genes == ("PfNF54_100037200", "PF3D7_1032400")


def test_an_audit_names_genomes_or_targets() -> None:
    with pytest.raises(
        ValidationError, match="names the genomes it screens or the gene targets"
    ):
        AuditScope(site_id="plasmodb")


def test_a_screened_genome_needs_a_check_and_a_check_needs_a_genome() -> None:
    with pytest.raises(ValidationError, match="a screened genome needs a check"):
        AuditScope(site_id="plasmodb", genomes=(NF54,))
    with pytest.raises(ValidationError, match="a screened genome needs a check"):
        AuditScope(site_id="plasmodb", checks=("gene_length",), targets=(PIGA_PAIR,))


def test_comparison_genomes_need_a_screened_genome() -> None:
    with pytest.raises(
        ValidationError, match="comparison genomes serve a screened genome"
    ):
        AuditScope(site_id="plasmodb", comparison=RELATIVES, targets=(PIGA_PAIR,))


def test_a_genome_is_named_once_across_audited_and_comparison() -> None:
    with pytest.raises(ValidationError, match="Plasmodium relative0 X is named twice"):
        AuditScope(
            site_id="plasmodb",
            genomes=(RELATIVES[0],),
            comparison=RELATIVES,
            checks=("gene_length",),
        )


def test_a_target_is_named_once() -> None:
    with pytest.raises(
        ValidationError,
        match="pseudogene_call:PfNF54_100037200\\+PF3D7_1032400 is named twice",
    ):
        AuditScope(site_id="plasmodb", targets=(PIGA_PAIR, PIGA_PAIR))


def test_more_than_eight_audited_genomes_is_refused() -> None:
    nine = tuple(f"Plasmodium falciparum strain{k}" for k in range(9))
    with pytest.raises(ValidationError, match="at most 8 whole genomes, not 9"):
        _admitted(site_id="plasmodb", genomes=nine, checks=("gene_length",))


def test_a_scope_reads_its_camel_case_wire_form() -> None:
    scope = AuditScope.model_validate(
        {
            "siteId": "plasmodb",
            "genomes": [NF54],
            "comparison": list(RELATIVES),
            "checks": ["gene_length", "gene_split"],
            "targets": [
                {
                    "check": "pseudogene_call",
                    "genes": ["PfNF54_100037200", "PF3D7_1032400"],
                }
            ],
        }
    )
    assert scope.confirm_limit == DEFAULT_CONFIRM_LIMIT
    assert scope.collected == (NF54, *RELATIVES)
    assert scope.roles[:2] == [(NF54, "audited"), (RELATIVES[0], "comparison")]
    assert scope.targets == (PIGA_PAIR,)
    assert (
        AuditScope.model_validate(scope.model_dump(by_alias=True, mode="json")) == scope
    )


def test_a_separator_inside_a_name_never_joins_two_targets_into_one_key() -> None:
    first = OrganelleTarget(
        check="organelle_join", genes=("G",), organism="O:X", sequence_id="C"
    )
    second = OrganelleTarget(
        check="organelle_join", genes=("G",), organism="O", sequence_id="X:C"
    )
    assert (first.key, second.key) == (
        "organelle_join:G:O%3AX:C",
        "organelle_join:G:O:X%3AC",
    )
    assert AuditScope(site_id="plasmodb", targets=(first, second)).targets == (
        first,
        second,
    )
    joined = GenePairTarget(check="strain_model", genes=("A+B", "C"))
    split = GenePairTarget(check="strain_model", genes=("A", "B+C"))
    assert (joined.key, split.key) == ("strain_model:A%2BB+C", "strain_model:A+B%2BC")
    escaped = MissingGeneTarget(
        check="missing_gene", genes=("A%3AB",), absent_organism="O"
    )
    colon = MissingGeneTarget(check="missing_gene", genes=("A:B",), absent_organism="O")
    assert (escaped.key, colon.key) == (
        "missing_gene:A%253AB:O",
        "missing_gene:A%3AB:O",
    )


def _absent_from(*genomes: str) -> tuple[MissingGeneTarget, ...]:
    return tuple(
        MissingGeneTarget(
            check="missing_gene", genes=("TGARI_257090",), absent_organism=genome
        )
        for genome in genomes
    )


STRAINS = tuple(f"Toxoplasma gondii strain{k}" for k in range(CAP + 1))


def test_a_missing_gene_genome_counts_toward_the_genome_cap() -> None:
    with pytest.raises(ValidationError, match="at most 8 whole genomes, not 9"):
        _admitted(
            site_id="toxodb",
            genomes=STRAINS[:1],
            checks=("gene_length",),
            targets=_absent_from(*STRAINS[1:]),
        )
    with pytest.raises(ValidationError, match="at most 8 whole genomes, not 9"):
        _admitted(
            site_id="toxodb",
            genomes=STRAINS[:5],
            checks=("gene_length",),
            targets=_absent_from(*STRAINS[5:]),
        )
    shared = _admitted(
        site_id="toxodb",
        genomes=STRAINS[:5],
        checks=("gene_length",),
        targets=_absent_from(*STRAINS[4:8]),
    )
    assert len(shared.targets) == 4


def _organelles(*genomes: str) -> tuple[OrganelleTarget, ...]:
    return tuple(
        OrganelleTarget(
            check="organelle_join",
            genes=("PF3D7_MIT02300",),
            organism=genome,
            sequence_id="MIT",
        )
        for genome in genomes
    )


PLASMODIA = tuple(f"Plasmodium falciparum strain{k}" for k in range(CAP + 1))


def test_an_organelle_genome_counts_toward_the_genome_cap() -> None:
    with pytest.raises(ValidationError, match="at most 8 whole genomes, not 9"):
        _admitted(site_id="plasmodb", targets=_organelles(*PLASMODIA))
    shared = _admitted(
        site_id="plasmodb",
        genomes=PLASMODIA[:4],
        checks=("gene_length",),
        targets=_organelles(*PLASMODIA[3:8]),
    )
    assert len(shared.targets) == 5


def _fusions(count: int) -> tuple[SingleGeneTarget, ...]:
    return tuple(
        SingleGeneTarget(check="gene_fusion", genes=(f"AK88_{k}",))
        for k in range(count)
    )


def test_fusion_and_missing_gene_targets_are_capped_together() -> None:
    assert MAX_UNNAMED_GENOME_TARGETS == 8
    with pytest.raises(
        ValidationError, match="at most 8 fusion and missing-gene targets, not 9"
    ):
        AuditScope(
            site_id="toxodb", targets=(*_fusions(5), *_absent_from(*STRAINS[:4]))
        )
    with pytest.raises(
        ValidationError, match="at most 8 fusion and missing-gene targets, not 9"
    ):
        AuditScope(site_id="plasmodb", targets=_fusions(9))
    held = AuditScope(
        site_id="toxodb", targets=(*_fusions(4), *_absent_from(*STRAINS[:4]))
    )
    assert len(held.targets) == MAX_UNNAMED_GENOME_TARGETS


def test_a_strain_or_window_target_counts_toward_no_genome_cap() -> None:
    strains = tuple(
        GenePairTarget(check="strain_model", genes=(f"PcyM_{k}", "PCYB_074210"))
        for k in range(CAP + 1)
    )
    lengths = tuple(
        SingleGeneTarget(check="gene_length", genes=(f"PcyM_L{k}",))
        for k in range(CAP + 1)
    )
    scope = _admitted(
        site_id="plasmodb",
        genomes=PLASMODIA[:8],
        checks=("gene_length",),
        targets=(*strains, *lengths, *_fusions(MAX_UNNAMED_GENOME_TARGETS)),
    )
    assert len(scope.targets) == 2 * (CAP + 1) + 8


P3D7 = "Plasmodium falciparum 3D7"


def test_a_pseudogene_screen_names_a_collected_reference_genome() -> None:
    with pytest.raises(
        ValidationError, match="a pseudogene screen names its reference genome"
    ):
        AuditScope(
            site_id="plasmodb",
            genomes=(NF54,),
            comparison=(P3D7,),
            checks=("pseudogene_call",),
        )
    with pytest.raises(
        ValidationError, match="the reference genome is one of the collected genomes"
    ):
        AuditScope(
            site_id="plasmodb",
            genomes=(NF54,),
            comparison=(P3D7,),
            checks=("pseudogene_call",),
            reference_genome="Plasmodium vivax P01",
        )
    scope = AuditScope(
        site_id="plasmodb",
        genomes=(NF54,),
        comparison=(P3D7,),
        checks=("pseudogene_call",),
        reference_genome=P3D7,
    )
    assert (scope.checks, scope.reference_genome) == (("pseudogene_call",), P3D7)
    assert scope.model_dump(by_alias=True, mode="json")["referenceGenome"] == P3D7


def test_a_reference_genome_serves_a_pseudogene_screen() -> None:
    with pytest.raises(
        ValidationError, match="a reference genome serves a pseudogene screen"
    ):
        AuditScope(
            site_id="plasmodb",
            genomes=(NF54,),
            comparison=(P3D7,),
            checks=("gene_length",),
            reference_genome=P3D7,
        )


def test_a_comparison_reference_genome_counts_toward_the_genome_cap() -> None:
    with pytest.raises(ValidationError, match="at most 8 whole genomes, not 9"):
        _admitted(
            site_id="plasmodb",
            genomes=PLASMODIA[:8],
            comparison=(P3D7,),
            checks=("pseudogene_call",),
            reference_genome=P3D7,
        )
    audited = _admitted(
        site_id="plasmodb",
        genomes=PLASMODIA[:8],
        checks=("pseudogene_call",),
        reference_genome=PLASMODIA[0],
    )
    assert audited.reference_genome == PLASMODIA[0]


EXAMPLES = tuple(f"Examplea alpha {letter}" for letter in "ABCDEFGH")
EXAMPLE_REFERENCE = "Examplea alpha R"
_REFERENCED: dict[str, object] = {
    "siteId": "exampledb",
    "genomes": list(EXAMPLES),
    "comparison": [EXAMPLE_REFERENCE],
    "checks": ["pseudogene_call"],
    "referenceGenome": EXAMPLE_REFERENCE,
}


def test_the_cap_counts_the_reference_genome() -> None:
    with pytest.raises(
        ValidationError, match="an audit reads at most 8 whole genomes, not 9"
    ):
        AuditScope.admitted(_REFERENCED, max_genomes=8)
    admitted = AuditScope.admitted(_REFERENCED, max_genomes=9)
    stored = AuditScope.model_validate(_REFERENCED)
    assert admitted == stored
    assert whole_genome_reads(stored) == frozenset({*EXAMPLES, EXAMPLE_REFERENCE})


def test_the_cap_counts_a_missing_gene_targets_absent_genome() -> None:
    raw: dict[str, object] = {
        "siteId": "exampledb",
        "genomes": list(EXAMPLES),
        "checks": ["gene_length"],
        "targets": [
            {
                "check": "missing_gene",
                "genes": ["EXA_0001"],
                "absentOrganism": EXAMPLE_REFERENCE,
            }
        ],
    }
    with pytest.raises(
        ValidationError, match="an audit reads at most 8 whole genomes, not 9"
    ):
        AuditScope.admitted(raw, max_genomes=8)
    assert AuditScope.admitted(raw, max_genomes=9).targets[0].genome == (
        EXAMPLE_REFERENCE
    )
    assert len(whole_genome_reads(AuditScope.model_validate(raw))) == 9
