"""The plasmodb drug-target request as criteria: three transcript leaves bound
with the values the framing pass gave them, and the compounds transform."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, SinglePickValue, StringValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.operational_spec import Criterion, StructureNode

PF = "Plasmodium falciparum 3D7"
RNASEQ = "GenesByRNASeqpfal3D7_Newbold_ebi_rnaSeq_RSRCPercentile"
HOURS = ["0 hours", "8 hours", "16 hours", "24 hours", "32 hours", "40 hours"]


def blood_stage(criterion_id: str, *, minimum: str = "80") -> Criterion:
    return Criterion(
        id=criterion_id,
        text="P. falciparum 3D7 genes expressed in the blood stage",
        search_name=RNASEQ,
        resolved_params={
            "profileset_generic": SinglePickValue(
                value="P. falciparum Newbold mRNA Seq dataunstranded"
            ),
            "samples_percentile_generic": MultiPickValue(values=HOURS),
            "min_expression_percentile": StringValue(value=minimum),
            "max_expression_percentile": StringValue(value="100"),
        },
        result_count=2_165,
    )


def low_variation(criterion_id: str) -> Criterion:
    return Criterion(
        id=criterion_id,
        text="P. falciparum 3D7 genes with variants per kb (CDS) <= 1 across isolates",
        search_name="GenesByNgsSnps",
        organism_param="organismSinglePick",
        resolved_params={
            "organismSinglePick": MultiPickValue(values=[PF]),
            "snp_density_lower": StringValue(value="0"),
            "snp_density_upper": StringValue(value="1"),
        },
        result_count=38,
    )


def no_human(criterion_id: str) -> Criterion:
    return Criterion(
        id=criterion_id,
        text="P. falciparum 3D7 genes with no human equivalent",
        search_name="GenesByOrthologPattern",
        resolved_params={
            "organism": MultiPickValue(values=[PF]),
            "profile_pattern": StringValue(value="%hsap:N%"),
            "excluded_species": StringValue(value="hsap"),
            "included_species": StringValue(value="n/a"),
        },
        result_count=2_812,
    )


def drug_target() -> Criterion:
    return Criterion(
        id="c_drug_target",
        text="P. falciparum 3D7 genes with drug-target or targetability evidence",
        search_name="GenesByCompoundsTransform",
        search_display_name="Transform to Genes",
        role="transform",
        organism_param="organism",
        resolved_params={"organism": MultiPickValue(values=[PF])},
    )


def leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def join(operator: CombineOp, *inputs: StructureNode) -> StructureNode:
    """A left-deep chain of ``operator`` over the inputs, as FRAME writes one."""
    joined = inputs[0]
    for node in inputs[1:]:
        joined = StructureNode(kind="combine", operator=operator, inputs=[joined, node])
    return joined


def three(blood: str, snps: str, human: str) -> StructureNode:
    """The three leaves, INTERSECTed in the order the framing pass wrote them."""
    return join(CombineOp.INTERSECT, leaf(blood), leaf(snps), leaf(human))
