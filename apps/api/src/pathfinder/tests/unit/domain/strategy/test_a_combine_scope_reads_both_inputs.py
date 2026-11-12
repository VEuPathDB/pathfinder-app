from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode

from pathfinder.domain.site_checks import (
    CountedOrganisms,
    OrganismCount,
    organism_check,
)
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    OrganismValue,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.organism_scope import (
    SelectedOrganisms,
    SiteTaxa,
    output_organisms,
)
from pathfinder.domain.strategy.orthology import (
    OrganismChange,
    organism_change,
    organism_move_refusal,
)
from pathfinder.domain.strategy.spec_fold import fold_organism_universe
from pathfinder.domain.strategy.validate import cross_organism_refusal
from pathfinder.tests._support.bound_values import bound

from ._builders import combine

_GT1 = "Toxoplasma gondii GT1"
_PK_H = "Plasmodium knowlesi strain H"
_PK_A1H1 = "Plasmodium knowlesi strain A1H1"
_PF = "Plasmodium falciparum 3D7"
_PV = "Plasmodium vivax P01"
_APICOMPLEXA = "Apicomplexa"
_PATTERN = "GenesByOrthologPattern"
_SIGNAL = "GenesWithSignalPeptide"
_ORTHOLOGS = "GenesByOrthologs"
_GT1_SCREEN = "GenesByPhenotypeEdaSubset_ToxoDB_tgonGT1_CrisprScreen_Phenotype_RSRC"
_GT1_PROFILE = (
    "GenesByPhenotypeEdaSubset_ToxoDB_tgonGT1_CrisprFunctionalProfiling_Phenotype_RSRC"
)
_PK_H_SCREEN = (
    "GenesByPhenotypeEdaSubset_PlasmoDB_pknoH_piggyBac_mutagenesis_HME_MIS_OIS_"
    "Phenotype_RSRC"
)
_PK_A1H1_SCREEN = (
    "GenesByPhenotypeEdaSubset_PlasmoDB_pknoA1H1_piggyBac_mutagenesis_MIS_MFS_"
    "Phenotype_RSRC"
)
_MARKED = {_PATTERN: "organism", _SIGNAL: "organism", _ORTHOLOGS: "organism"}
_DATASETS = {
    "gt1_screen": frozenset({_GT1}),
    "gt1_profile": frozenset({_GT1}),
    "pk_h": frozenset({_PK_H}),
    "pk_a1h1": frozenset({_PK_A1H1}),
}
_TAXA = SiteTaxa(
    under={_APICOMPLEXA: frozenset({_GT1, _PK_H, _PK_A1H1, _PF, _PV})},
    listed=frozenset({_GT1, _PK_H, _PK_A1H1, _PF, _PV}),
)


def _experiment(step_id: str, search_name: str) -> StrategyStepNode:
    return StrategyStepNode(id=step_id, search_name=search_name)


def _marked(step_id: str, search_name: str, organism: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name=search_name,
        parameters={"organism": MultiPickValue(values=[organism])},
    )


def _screens() -> StrategyStepNode:
    gt1 = combine(
        "u1",
        _experiment("gt1_screen", _GT1_SCREEN),
        _experiment("gt1_profile", _GT1_PROFILE),
        CombineOp.UNION,
    )
    with_h = combine("u2", gt1, _experiment("pk_h", _PK_H_SCREEN), CombineOp.UNION)
    return combine(
        "u3", with_h, _experiment("pk_a1h1", _PK_A1H1_SCREEN), CombineOp.UNION
    )


def _measured(*, screens_first: bool) -> StrategyStepNode:
    pattern = _marked("pattern", _PATTERN, _APICOMPLEXA)
    if screens_first:
        return combine("intersect", _screens(), pattern)
    return combine("intersect", pattern, _screens())


@pytest.mark.parametrize("screens_first", [True, False])
def test_every_screen_of_the_intersect_selects_its_organism(
    screens_first: bool,
) -> None:
    found = output_organisms(_measured(screens_first=screens_first), _MARKED, _DATASETS)
    tally = CountedOrganisms(
        step="227354010 ('Intersect')",
        total=891,
        rows=[
            OrganismCount(organism=_PK_A1H1, count=317),
            OrganismCount(organism=_PK_H, count=134),
            OrganismCount(organism=_GT1, count=440),
        ],
    )
    selected = SelectedOrganisms(entries=frozenset(found or ()), taxa=_TAXA)

    assert (found, organism_check("result", "", selected, tally).status) == (
        {_GT1, _PK_H, _PK_A1H1, _APICOMPLEXA},
        "pass",
    )


def _union(first: StrategyStepNode, second: StrategyStepNode) -> StrategyStepNode:
    return combine("union", first, second, CombineOp.UNION)


def test_a_union_side_that_holds_the_other_organism_is_not_refused() -> None:
    side = _union(
        _experiment("pk_h", _PK_H_SCREEN), _experiment("gt1_screen", _GT1_SCREEN)
    )
    root = combine("intersect", side, _marked("signal", _SIGNAL, _GT1))

    assert [
        output_organisms(side, _MARKED, _DATASETS),
        cross_organism_refusal(root, root, _MARKED, _DATASETS),
    ] == [{_PK_H, _GT1}, None]


def test_a_union_of_two_experiments_is_refused_with_both_searches() -> None:
    side = _union(
        _experiment("pk_h", _PK_H_SCREEN), _experiment("pk_a1h1", _PK_A1H1_SCREEN)
    )
    root = combine("intersect", side, _marked("signal", _SIGNAL, _PF))

    assert cross_organism_refusal(root, root, _MARKED, _DATASETS) == (
        f"Cannot INTERSECT steps with different organism scopes ({_PK_A1H1}, "
        f"{_PK_H} vs {_PF}). Gene IDs from different organisms never match, so "
        f"this always returns 0 results. The {_PK_A1H1_SCREEN}, {_PK_H_SCREEN} "
        f"searches run on experiments of {_PK_A1H1}, {_PK_H}, and no parameter "
        f"changes that organism. Map that side to {_PF} with a GenesByOrthologs "
        f"transform."
    )


def test_a_side_with_a_parameter_organism_is_not_fixed_by_its_experiment() -> None:
    side = _union(
        _experiment("pk_h", _PK_H_SCREEN), _marked("signal", _SIGNAL, _PK_A1H1)
    )
    root = combine("intersect", side, _marked("other", _SIGNAL, _PF))

    assert cross_organism_refusal(root, root, _MARKED, _DATASETS) == (
        f"Cannot INTERSECT steps with different organism scopes ({_PK_A1H1}, "
        f"{_PK_H} vs {_PF}). Gene IDs from different organisms never match, so "
        f"this always returns 0 results. Scope every seed to one organism: "
        f"{_PK_A1H1}, {_PK_H} or {_PF}."
    )


def _carried(step_id: str, organism: str, input_: StrategyStepNode) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id,
        search_name=_ORTHOLOGS,
        parameters={"organism": MultiPickValue(values=[organism])},
        primary_input=input_,
    )


def test_a_union_of_two_organisms_changes_no_organism() -> None:
    root = _union(_marked("pf", _SIGNAL, _PF), _marked("pv", _SIGNAL, _PV))
    carried = _carried("to_pf", _PF, root)

    assert [organism_change(root, _MARKED), organism_change(carried, _MARKED)] == [
        None,
        OrganismChange(seed=[_PF, _PV], records=[_PF]),
    ]


def test_a_carried_side_names_every_organism_the_searches_ran_on() -> None:
    carried = _carried("to_pv", _PV, _marked("pf", _SIGNAL, _PF))
    root = combine("intersect", carried, _marked("pv", _SIGNAL, _PV))

    assert organism_change(root, _MARKED) == OrganismChange(
        seed=[_PF, _PV], records=[_PV]
    )


def _criterion(criterion_id: str, organism: str) -> Criterion:
    return Criterion(
        id=criterion_id,
        text=f"signal peptide in {organism}",
        search_name=_SIGNAL,
        organism_param="organism",
        resolved_params=bound({"organism": MultiPickValue(values=[organism])}),
    )


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _joined(operator: CombineOp, *inputs: StructureNode) -> StructureNode:
    return StructureNode(kind="combine", operator=operator, inputs=list(inputs))


def _spec(root: StructureNode, *criteria: Criterion) -> OperationalSpec:
    return OperationalSpec(criteria=list(criteria), structure=SpecStructure(root=root))


def test_a_narrowing_under_a_union_of_two_organisms_is_not_refused() -> None:
    held = _joined(CombineOp.UNION, _leaf("c_pf"), _leaf("c_pv"))
    criteria = (_criterion("c_pf", _PF), _criterion("c_pv", _PV))
    edited = _joined(CombineOp.INTERSECT, _leaf("c_narrow"), held)
    widened = _joined(CombineOp.UNION, _leaf("c_narrow"), held)
    narrow = _criterion("c_narrow", _PV)

    assert [
        organism_move_refusal(
            "tighten",
            before=_spec(held, *criteria),
            after=_spec(edited, *criteria, narrow),
        ),
        organism_move_refusal(
            "loosen",
            before=_spec(held, *criteria),
            after=_spec(widened, *criteria, narrow),
        ),
    ] == [None, None]


def _organism(organism: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.ORGANISM,
        requested_value=organism,
        label="organism",
        source=ConstraintSource.USER_EXPLICIT,
        value=OrganismValue(organism=organism),
    )


def _organism_leaf(*requirements: Constraint) -> Criterion:
    return _criterion("c_named", _PF).model_copy(
        update={"answers": [RequirementLink(requirement=c.id) for c in requirements]}
    )


def test_an_organism_leaf_beside_a_wider_union_stays() -> None:
    pf = _organism(_PF)
    root = _joined(
        CombineOp.INTERSECT,
        _leaf("c_named"),
        _joined(CombineOp.UNION, _leaf("c_pf"), _leaf("c_pv")),
    )
    spec = _spec(
        root, _organism_leaf(pf), _criterion("c_pf", _PF), _criterion("c_pv", _PV)
    )

    folded = fold_organism_universe(
        spec, SpecStructure(root=root), (_PF, _PV), (pf,), {}, live_step_ids=()
    )

    assert (folded.structure.root, folded.dropped) == (root, ())


def test_a_union_that_carries_both_organisms_names_both_carriers() -> None:
    pf, pv = _organism(_PF), _organism(_PV)
    root = _joined(
        CombineOp.INTERSECT,
        _leaf("c_named"),
        _joined(CombineOp.UNION, _leaf("c_pf"), _leaf("c_pv")),
    )
    spec = _spec(
        root, _organism_leaf(pf, pv), _criterion("c_pf", _PF), _criterion("c_pv", _PV)
    )

    folded = fold_organism_universe(
        spec, SpecStructure(root=root), (_PF, _PV), (pf, pv), {}, live_step_ids=()
    )

    assert [(d.criterion_id, d.carrier_ids) for d in folded.dropped] == [
        ("c_named", ("c_pf", "c_pv"))
    ]
    assert folded.dropped[0].fate == (
        f"c_named ('signal peptide in {_PF}') is dropped: it links only the "
        f"organism {_PF}, {_PV}, which c_pf, c_pv already run on, so that "
        f"organism value meets it."
    )


def test_a_reversed_minus_is_carried_by_its_secondary_input() -> None:
    pf = _organism(_PF)
    root = _joined(
        CombineOp.INTERSECT,
        _leaf("c_named"),
        _joined(CombineOp.RMINUS, _leaf("c_pv"), _leaf("c_pf")),
    )
    spec = _spec(
        root, _organism_leaf(pf), _criterion("c_pf", _PF), _criterion("c_pv", _PV)
    )

    folded = fold_organism_universe(
        spec, SpecStructure(root=root), (_PF, _PV), (pf,), {}, live_step_ids=()
    )

    assert [(d.criterion_id, d.carrier_ids) for d in folded.dropped] == [
        ("c_named", ("c_pf",))
    ]
