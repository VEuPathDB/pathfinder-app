"""A transform runs only on an input step of a record class it declares, so a
tree that feeds it another record class is refused before anything is built."""

from __future__ import annotations

from collections.abc import Mapping

from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.orthology import stated_steps
from pathfinder.domain.strategy.validate import (
    SearchRecordClasses,
    transform_input_refusal,
)
from pathfinder.tests.unit.domain.strategy._n1_tree import (
    RNASEQ,
    blood_stage,
    drug_target,
    join,
    leaf,
    low_variation,
    no_human,
    three,
)
from pathfinder.tests.unit.domain.strategy._orthology import (
    kept_by_intersect,
    round_trip_spec,
    seed_node,
)

# The record classes plasmodb declares for each search the trees run.
CLASSES = {
    RNASEQ: SearchRecordClasses(display_name="RNA-Seq", returns="transcript"),
    "GenesByNgsSnps": SearchRecordClasses(display_name="SNPs", returns="transcript"),
    "GenesByOrthologPattern": SearchRecordClasses(
        display_name="Orthology Phylogenetic Profile", returns="transcript"
    ),
    "GenesByCompoundsTransform": SearchRecordClasses(
        display_name="Transform to Genes", returns="transcript", takes=("compound",)
    ),
    "GenesWithSignalPeptide": SearchRecordClasses(
        display_name="Predicted Signal Peptide", returns="transcript"
    ),
    "GenesByTransmembraneDomains": SearchRecordClasses(
        display_name="Transmembrane Domain Count", returns="transcript"
    ),
    "GenesByOrthologs": SearchRecordClasses(
        display_name="Transform by Orthology",
        returns="transcript",
        takes=("transcript",),
    ),
    "CompoundsByTextSearch": SearchRecordClasses(
        display_name="Text", returns="compound"
    ),
}
# The plural display name of each record class, as plasmodb publishes it.
NAMES = {"transcript": "Genes", "compound": "Compounds"}


def _n1_spec(root: StructureNode) -> OperationalSpec:
    return OperationalSpec(
        criteria=[
            blood_stage("step_9ba9dec1"),
            low_variation("step_3a4dba81"),
            no_human("step_0ae0f092"),
            drug_target(),
        ],
        structure=SpecStructure(root=root),
    )


def _refusal(
    spec: OperationalSpec, classes: Mapping[str, SearchRecordClasses] = CLASSES
) -> str | None:
    steps = stated_steps(spec)
    assert steps is not None
    return transform_input_refusal(steps, classes, NAMES)


def test_a_compounds_transform_over_genes_is_refused() -> None:
    existing = three("step_9ba9dec1", "step_3a4dba81", "step_0ae0f092")
    mapped = StructureNode(
        kind="transform",
        criterion_id="c_drug_target",
        inputs=[StructureNode(kind="copy", inputs=[existing.model_copy(deep=True)])],
    )
    spec = _n1_spec(join(CombineOp.INTERSECT, existing, mapped))

    assert _refusal(spec) == (
        "c_drug_target runs Transform to Genes (GenesByCompoundsTransform), which "
        "takes Compounds as its input step, and the subtree under it returns "
        "Genes. WDK runs a transform only on the record classes it declares, so "
        "this tree cannot run. Transform to Genes maps Compounds to Genes; it is "
        "not a filter on Genes. Drop c_drug_target, bind it to a search on Genes "
        "that states it, or ask the researcher."
    )


def _genes_under_the_transform() -> OperationalSpec:
    return _n1_spec(
        StructureNode(
            kind="transform",
            criterion_id="c_drug_target",
            inputs=[leaf("step_9ba9dec1")],
        )
    )


def _compounds_under_the_transform() -> OperationalSpec:
    return OperationalSpec(
        criteria=[
            drug_target(),
            blood_stage("c_blood").model_copy(
                update={"id": "c_compounds", "search_name": "CompoundsByTextSearch"}
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="transform",
                criterion_id="c_drug_target",
                inputs=[leaf("c_compounds")],
            )
        ),
    )


def test_a_transform_over_a_class_it_takes_or_an_undeclared_one_is_accepted() -> None:
    """A declared input class, no declared list, and an input of unknown class
    each leave the tree unrefused."""
    undeclared = {
        **CLASSES,
        "GenesByCompoundsTransform": SearchRecordClasses(
            display_name="Transform to Genes", returns="transcript"
        ),
    }
    unread = {name: c for name, c in CLASSES.items() if name != RNASEQ}

    refusals = {
        "compounds under the compounds transform": _refusal(
            _compounds_under_the_transform()
        ),
        "the orthology round trip over genes": _refusal(
            round_trip_spec(kept_by_intersect(seed_node()))
        ),
        "a transform that declares no input class": _refusal(
            _genes_under_the_transform(), undeclared
        ),
        "an input of unknown class": _refusal(_genes_under_the_transform(), unread),
    }

    assert refusals == dict.fromkeys(refusals)


def test_a_combine_answers_with_the_class_of_either_known_input() -> None:
    existing = three("step_9ba9dec1", "step_3a4dba81", "step_0ae0f092")
    spec = _n1_spec(
        StructureNode(kind="transform", criterion_id="c_drug_target", inputs=[existing])
    )
    unread = {name: c for name, c in CLASSES.items() if name != RNASEQ}

    refusal = _refusal(spec, unread)

    assert refusal is not None
    assert refusal.startswith(
        "c_drug_target runs Transform to Genes (GenesByCompoundsTransform), which "
        "takes Compounds as its input step, and the subtree under it returns Genes."
    )


def test_a_combine_of_two_known_record_classes_is_refused() -> None:
    """A compounds input beside a genes input cannot answer for the combine."""
    spec = _compounds_under_the_transform()
    spec = spec.model_copy(
        update={
            "criteria": [*spec.criteria, blood_stage("step_9ba9dec1")],
            "structure": SpecStructure(
                root=StructureNode(
                    kind="transform",
                    criterion_id="c_drug_target",
                    inputs=[
                        join(
                            CombineOp.INTERSECT,
                            leaf("c_compounds"),
                            leaf("step_9ba9dec1"),
                        )
                    ],
                )
            ),
        }
    )

    assert _refusal(spec) == (
        "The subtree under c_drug_target joins Compounds and Genes in one "
        "combine. WDK combines only steps of one record class, so this tree "
        "cannot run. Bind every input under c_drug_target to a search on "
        "Compounds, or ask the researcher."
    )
