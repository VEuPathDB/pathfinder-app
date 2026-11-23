from __future__ import annotations

import json
from pathlib import Path

from veupathdb.domain.parameters import MultiPickValue, SinglePickValue, StringValue
from veupathdb.domain.strategy import CombineOp

from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    OrganismValue,
)
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.spec_fold import fold_organism_universe
from strategist.tests._support.bound_values import bound

_A2 = json.loads(
    (
        Path(__file__).resolve().parents[3]
        / "fixtures"
        / "turns"
        / "a2_epitope_fold.json"
    ).read_text()
)
_PF = "Plasmodium falciparum 3D7"
_PF_GENES = 5_720
_R1 = Constraint(
    id=_A2["organismRequirement"]["id"],
    kind=ConstraintKind.ORGANISM,
    requested_value=_A2["organismRequirement"]["requestedValue"],
    label=_A2["organismRequirement"]["label"],
    quote=_A2["organismRequirement"]["quote"],
    source=ConstraintSource.USER_EXPLICIT,
    value=OrganismValue(organism=_PF),
)


def _epitope(*, defaulted: tuple[str, ...] = ()) -> Criterion:
    args = _A2["epitope"]["args"]
    params = args["params"]
    return Criterion(
        id=args["criterion_id"],
        text=args["text"],
        answers=[RequirementLink(requirement=_R1.id, param="organism")],
        search_name=args["search_name"],
        role=args["role"],
        organism_param="organism",
        resolved_params=bound(
            {
                "organism": MultiPickValue(values=[_PF]),
                "peptide_mismatch": SinglePickValue(value=params["peptide_mismatch"]),
                "taxon_match": SinglePickValue(value=params["taxon_match"]),
                "protein_match": SinglePickValue(value=params["protein_match"]),
            },
            defaulted=list(defaulted),
        ),
        result_count=882,
    )


def _phylogeny() -> Criterion:
    args = _A2["phylogeny"]["args"]
    params = args["params"]
    return Criterion(
        id=args["criterion_id"],
        text=args["text"],
        search_name=args["search_name"],
        role=args["role"],
        organism_param="organism",
        resolved_params=bound(
            {
                "organism": MultiPickValue(values=params["organism"]),
                "included_species": StringValue(value=params["included_species"]),
                "excluded_species": StringValue(value=params["excluded_species"]),
            }
        ),
        result_count=2_876,
    )


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def test_the_a2_epitope_leaf_narrows_and_stays() -> None:
    root = StructureNode(
        kind="combine",
        operator=CombineOp.INTERSECT,
        inputs=[_leaf("c_phylogeny"), _leaf("c_epitope")],
    )
    tree = SpecStructure(root=root)
    spec = OperationalSpec(criteria=[_phylogeny(), _epitope()], structure=tree)

    folded = fold_organism_universe(
        spec, tree, [_PF], {"c_epitope": _PF_GENES}, live_step_ids=()
    )

    assert folded.dropped == ()
    assert folded.structure.root == root


def test_a_leaf_that_counts_the_organism_universe_is_still_dropped() -> None:
    unset = ("peptide_mismatch", "taxon_match", "protein_match")
    whole = _epitope(defaulted=unset).model_copy(update={"result_count": _PF_GENES})
    root = StructureNode(
        kind="combine",
        operator=CombineOp.INTERSECT,
        inputs=[_leaf("c_phylogeny"), _leaf("c_epitope")],
    )
    tree = SpecStructure(root=root)
    spec = OperationalSpec(criteria=[_phylogeny(), whole], structure=tree)

    folded = fold_organism_universe(
        spec, tree, [_PF], {"c_epitope": _PF_GENES}, live_step_ids=()
    )

    assert folded.structure.root == _leaf("c_phylogeny")
    assert [d.fate for d in folded.dropped] == [
        (
            f"c_epitope ('{whole.text}') is dropped: it matches all 5,720 genes "
            f"of {_PF}, which c_phylogeny already runs on, so it narrows nothing."
        )
    ]
