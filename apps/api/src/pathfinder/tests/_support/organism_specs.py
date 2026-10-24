from __future__ import annotations

from veupathdb.domain.parameters import (
    InputDatasetValue,
    MultiPickValue,
    StringValue,
)
from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests._support.bound_values import bound

ME49 = Constraint(
    kind=ConstraintKind.ORGANISM,
    label="organism",
    requested_value="Toxoplasma gondii ME49",
    source=ConstraintSource.USER_EXPLICIT,
)
PF3D7 = Constraint(
    kind=ConstraintKind.ORGANISM,
    label="organism",
    requested_value="Plasmodium falciparum 3D7",
    source=ConstraintSource.USER_EXPLICIT,
)
PROTEINS = Constraint(
    kind=ConstraintKind.RECORD_TYPE,
    label="record type",
    requested_value="proteins",
    source=ConstraintSource.USER_EXPLICIT,
)


def groups() -> Criterion:
    return Criterion(
        id="c_groups",
        text="groups with a ME49 protein and no mammal protein",
        search_name="GroupsByPhyleticPattern",
        record_class="group",
        resolved_params=bound(
            {"phyletic_expression": StringValue(value="tgon>=1T AND MAMM=0T")}
        ),
    )


def proteins() -> Criterion:
    return Criterion(
        id="c_proteins",
        text="their proteins",
        search_name="FromGroups",
        record_class="sequence",
        role="transform",
    )


def taxon() -> Criterion:
    return Criterion(
        id="c_me49",
        text="ME49 proteins",
        search_name="ByTaxonomy",
        record_class="sequence",
        resolved_params=bound({"taxon_type_ahead": MultiPickValue(values=["tgon"])}),
    )


def chain(*criteria: Criterion) -> OperationalSpec:
    groups, proteins, *rest = criteria
    transform = StructureNode(
        kind="transform",
        criterion_id=proteins.id,
        inputs=[StructureNode(kind="leaf", criterion_id=groups.id)],
    )
    root = (
        StructureNode(
            kind="combine",
            operator=CombineOp.INTERSECT,
            inputs=[transform, StructureNode(kind="leaf", criterion_id=rest[0].id)],
        )
        if rest
        else transform
    )
    return OperationalSpec(
        goal="ME49 proteins in groups with no mammal member",
        criteria=list(criteria),
        structure=SpecStructure(root=root),
    )


def id_list() -> Criterion:
    return Criterion(
        id="c_ids",
        text="these genes",
        search_name="GeneByLocusTag",
        record_class="transcript",
        resolved_params=bound({"ds_gene_ids": InputDatasetValue(dataset_id="1234567")}),
    )


def signal_peptide() -> Criterion:
    return Criterion(
        id="c_signal",
        text="genes with a signal peptide",
        search_name="GenesWithSignalPeptide",
        record_class="transcript",
    )


def single(criterion: Criterion) -> OperationalSpec:
    return OperationalSpec(
        goal=criterion.text,
        criteria=[criterion],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id=criterion.id)
        ),
    )
