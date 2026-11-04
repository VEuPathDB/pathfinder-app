from __future__ import annotations

from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    PhyleticBinding,
    PhyleticTree,
    StringValue,
    derive_binding,
    to_wire,
)
from veupathdb.domain.strategy import (
    CombineOp,
    StrategyAst,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb.wdk import phyletic_tree_of

from pathfinder.domain.strategy.genome_group import GenomeGroup
from pathfinder.domain.strategy.genome_group_steps import (
    criterion_keeping_its_reading,
    spec_read_on_genomes,
    spec_with_group_steps,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    Measurement,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.operations import (
    AddCombineOp,
    DeleteStepOp,
    GraphOperation,
    UpdateStepParamsOp,
)
from pathfinder.domain.strategy.outside_changes import outside_changes
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_diff import diff_specs
from pathfinder.domain.strategy.spec_fold import fold_option_criteria
from pathfinder.domain.strategy.spec_hydration import StepReading
from pathfinder.domain.strategy.spec_replay import spec_replaying
from pathfinder.domain.strategy.spec_to_operations import operations_for
from pathfinder.domain.strategy.spec_tree import build_step_tree, renumber_criteria
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests._support.recorded_counts import CRYPTO_IOWA, TGON_STRAINS
from pathfinder.tests._support.recorded_searches import suite_search

_TREE = phyletic_tree_of(
    list(suite_search("search_genes_by_ortholog_pattern").parameters or [])
)
_PLASMODIUM = tuple(
    sorted(
        node.code
        for node in (_TREE or PhyleticTree()).nodes()
        if "Plasmodium" in node.label and not node.clade
    )
)
_ID = "c_profile"
_RIGHT = f"{_ID}_absent"
_PAIR = ("pber", "pfal")
_STRAINS = [
    Measurement(kind="any_strain", param="included_species", count=1259),
    Measurement(kind="all_strains", param="included_species", count=501),
]


def _wire(included: list[str], excluded: list[str]) -> dict[str, str]:
    assert _TREE is not None
    derived = derive_binding(_TREE, included, excluded)
    assert isinstance(derived, PhyleticBinding)
    return derived.model_dump()


def _profile(
    included: list[str],
    excluded: list[str],
    group: GenomeGroup | None = None,
    *,
    criterion_id: str = _ID,
) -> Criterion:
    values: dict[str, ParamValue] = {
        "organism": MultiPickValue(values=[CRYPTO_IOWA]),
        **{
            name: StringValue(value=value)
            for name, value in _wire(included, excluded).items()
        },
    }
    return Criterion(
        id=criterion_id,
        text="an ortholog in the group",
        search_name="GenesByOrthologPattern",
        record_class="transcript",
        role="seed",
        result_count=501,
        genome_group=group,
        measurements=_STRAINS,
        resolved_params=bound(values),
    )


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _spec(criterion: Criterion) -> OperationalSpec:
    return OperationalSpec(
        goal="orthologs",
        criteria=[criterion],
        structure=SpecStructure(root=_leaf(criterion.id)),
    )


def _at_least_one(*genomes: str) -> GenomeGroup:
    return GenomeGroup(reading="at_least_one", genomes=genomes)


def _lists(criterion: Criterion) -> dict[str, str]:
    return {
        name: to_wire(criterion.resolved_params[name].value)
        for name in ("profile_pattern", "included_species", "excluded_species")
    }


def _read(spec: OperationalSpec, group: GenomeGroup) -> OperationalSpec:
    return spec_read_on_genomes(spec, _ID, group)


def test_the_recorded_tree_holds_the_group_of_61() -> None:
    assert len(_PLASMODIUM) == 61


def test_all_leaves_the_binding_and_the_step_count_and_settles() -> None:
    spec = _spec(_profile([*_PLASMODIUM], [*TGON_STRAINS]))

    read = _read(spec, GenomeGroup(reading="all", genomes=_PLASMODIUM))

    [settled] = read.criteria
    assert settled.param_values == spec.criteria[0].param_values
    assert settled.result_count == 501
    assert settled.genome_group == GenomeGroup(reading="all", genomes=_PLASMODIUM)
    assert read.structure == spec.structure
    assert build_step_tree(read).root.operator is None


def test_at_least_one_builds_a_left_minus_a_right_on_the_exact_wire() -> None:
    read = _read(_spec(_profile(["pber", "pfal"], ["mmus"])), _at_least_one(*_PAIR))

    root = build_step_tree(read).root

    assert root.operator is CombineOp.MINUS
    assert root.primary_input is not None
    assert root.secondary_input is not None
    assert (
        to_wire(root.primary_input.parameters["profile_pattern"]),
        to_wire(root.primary_input.parameters["included_species"]),
        to_wire(root.primary_input.parameters["excluded_species"]),
    ) == ("%mmus:N%", "n/a", "mmus")
    assert (
        to_wire(root.secondary_input.parameters["profile_pattern"]),
        to_wire(root.secondary_input.parameters["included_species"]),
    ) == ("%mmus:N%pber:N%pfal:N%", "n/a")
    assert to_wire(root.secondary_input.parameters["organism"]) == to_wire(
        root.primary_input.parameters["organism"]
    )


def test_another_required_genome_stays_on_both_sides() -> None:
    read = _read(
        _spec(_profile(["hsap", "pber", "pfal"], ["mmus"])), _at_least_one(*_PAIR)
    )

    left, right = read.criteria
    assert _lists(left)["profile_pattern"] == "%hsap:Y%mmus:N%"
    assert _lists(right)["profile_pattern"] == "%hsap:Y%mmus:N%pber:N%pfal:N%"
    assert (right.role, right.absence_of, left.result_count) == ("exclude", _ID, None)
    assert read.structure == SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.MINUS,
            inputs=[_leaf(_ID), _leaf(_RIGHT)],
        )
    )


def test_with_nothing_else_stated_the_left_states_no_constraint() -> None:
    left, right = _read(
        _spec(_profile(["pber", "pfal"], [])), _at_least_one(*_PAIR)
    ).criteria

    assert _lists(left) == {
        "profile_pattern": "%",
        "included_species": "n/a",
        "excluded_species": "n/a",
    }
    assert _lists(right)["profile_pattern"] == "%pber:N%pfal:N%"


def test_the_derivation_is_idempotent() -> None:
    read = _read(_spec(_profile(["pber", "pfal"], ["mmus"])), _at_least_one(*_PAIR))

    assert spec_with_group_steps(read) == read
    assert fold_option_criteria(read).spec == read


def test_a_rebind_of_the_strict_values_keeps_the_reading_and_folds_the_minus() -> None:
    read = _read(_spec(_profile(["pber", "pfal"], ["mmus"])), _at_least_one(*_PAIR))
    left, right = read.criteria

    kept = criterion_keeping_its_reading(left, _profile(["pber", "pfal"], ["mmus"]))
    folded = fold_option_criteria(
        read.model_copy(update={"criteria": [kept, right]})
    ).spec

    assert kept.genome_group == _at_least_one(*_PAIR)
    assert [_lists(c)["profile_pattern"] for c in folded.criteria] == [
        "%mmus:N%",
        "%mmus:N%pber:N%pfal:N%",
    ]


def test_a_rebind_of_the_left_keeps_the_reading() -> None:
    read = _read(_spec(_profile(["pber", "pfal"], ["mmus"])), _at_least_one(*_PAIR))
    left = read.criteria[0]

    kept = criterion_keeping_its_reading(
        left, left.model_copy(update={"genome_group": None})
    )

    assert kept.genome_group == _at_least_one(*_PAIR)


def test_a_rebind_of_other_genomes_gives_up_the_reading() -> None:
    read = _read(_spec(_profile(["pber", "pfal"], [])), _at_least_one(*_PAIR))

    kept = criterion_keeping_its_reading(read.criteria[0], _profile(["hsap"], []))

    assert (kept.genome_group, _lists(kept)["profile_pattern"]) == (None, "%hsap:Y%")


def _graph_of(root: StrategyStepNode) -> StrategyGraph:
    graph = StrategyGraph(graph_id="g", name="g", site_id="cryptodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    graph.last_step_id = root.id
    return graph


def _built() -> tuple[OperationalSpec, StrategyGraph, StrategyAst]:
    read = _read(_spec(_profile(["pber", "pfal"], ["hsap"])), _at_least_one(*_PAIR))
    tree = build_step_tree(read)
    spec = renumber_criteria(read, tree.step_id_by_criterion)
    return (
        spec,
        _graph_of(tree.root),
        StrategyAst(record_type="transcript", root=tree.root),
    )


def _plan(
    before: OperationalSpec, after: OperationalSpec, graph: StrategyGraph
) -> list[GraphOperation]:
    folded = fold_option_criteria(after, live_step_ids=graph.steps).spec
    return operations_for(diff_specs(before, folded), after=folded, graph=graph)


def _sides(spec: OperationalSpec) -> tuple[Criterion, Criterion]:
    right = next(c for c in spec.criteria if c.absence_of)
    return next(c for c in spec.criteria if c.id == right.absence_of), right


def test_an_edit_of_the_exclusion_updates_both_steps_and_adds_none() -> None:
    spec, graph, _ = _built()
    left, right = _sides(spec)
    edited = _profile(
        ["pber", "pfal"], ["mmus"], _at_least_one(*_PAIR), criterion_id=left.id
    )

    ops = _plan(spec, spec.model_copy(update={"criteria": [edited, right]}), graph)

    assert {op.kind for op in ops} == {"updateStepParams"}
    moved = {
        op.step_id: op.parameters for op in ops if isinstance(op, UpdateStepParamsOp)
    }
    assert to_wire(moved[left.id]["profile_pattern"]) == "%mmus:N%"
    assert to_wire(moved[right.id]["profile_pattern"]) == "%mmus:N%pber:N%pfal:N%"


def test_an_edit_that_gives_up_the_reading_deletes_the_right() -> None:
    spec, graph, _ = _built()
    left, right = _sides(spec)
    plain = _profile(["pfal"], ["hsap"], criterion_id=left.id)

    ops = _plan(spec, spec.model_copy(update={"criteria": [plain, right]}), graph)

    assert [op.step_id for op in ops if isinstance(op, DeleteStepOp)] == [right.id]
    assert not [op for op in ops if isinstance(op, AddCombineOp)]


def test_a_saved_strategy_replays_with_the_reading_it_still_holds() -> None:
    spec, _graph, ast = _built()

    replayed = spec_replaying(
        spec, outside_changes(ast, ast), ast, StepReading(sheet_params={}, listed={})
    )

    assert replayed.criteria == spec.criteria
    assert spec_with_group_steps(replayed) == replayed


def _with_pattern(
    node: StrategyStepNode, step_id: str, pattern: str
) -> StrategyStepNode:
    if node.id == step_id:
        moved: dict[str, ParamValue] = {
            **node.parameters,
            "profile_pattern": StringValue(value=pattern),
        }
        return node.model_copy(update={"parameters": moved})
    updates: dict[str, StrategyStepNode] = {}
    if node.primary_input is not None:
        updates["primary_input"] = _with_pattern(node.primary_input, step_id, pattern)
    if node.secondary_input is not None:
        updates["secondary_input"] = _with_pattern(
            node.secondary_input, step_id, pattern
        )
    return node.model_copy(update=updates)


def test_a_step_moved_outside_retires_the_reading_and_keeps_both_steps() -> None:
    spec, _graph, ast = _built()
    left, right = _sides(spec)
    live = ast.model_copy(
        update={"root": _with_pattern(ast.root, right.id, "%hsap:N%pfal:N%")}
    )

    replayed = spec_replaying(
        spec, outside_changes(ast, live), live, StepReading(sheet_params={}, listed={})
    )

    assert [c.id for c in replayed.criteria] == [left.id, right.id]
    assert [c.genome_group for c in replayed.criteria] == [None, None]
    assert [c.absence_of for c in replayed.criteria] == ["", ""]
    assert [m.kind for c in replayed.criteria for m in c.measurements] == []
    assert spec_with_group_steps(replayed) is replayed
