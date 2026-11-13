from __future__ import annotations

from veupathdb.domain.strategy import CombineOp

from strategist.domain.requirement_checks import record_type_check
from strategist.domain.site_checks import SiteCheck
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    RecordRole,
    RecordTypeValue,
)
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    structure_criteria,
)

_PATTERN = "GroupsByPhyleticPattern"


def _criterion(criterion_id: str, search_name: str, record_class: str) -> Criterion:
    return Criterion(
        id=criterion_id,
        text=criterion_id,
        search_name=search_name,
        record_class=record_class,
    )


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _pattern_spec() -> OperationalSpec:
    return OperationalSpec(
        criteria=[_criterion("step_b08116fe", _PATTERN, "group")],
        structure=SpecStructure(root=_leaf("step_b08116fe")),
    )


def _kinase_spec() -> OperationalSpec:
    return OperationalSpec(
        criteria=[
            _criterion("step_e97903fe", "GroupsByPFamIdOrKeyword", "group"),
            _criterion("step_54ce1477", "ByTaxonomy", "sequence"),
            _criterion("step_f319e55c", "FromGroups", "sequence"),
            _criterion("step_59c230ac", "GroupsFromSequences", "group"),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="transform",
                criterion_id="step_59c230ac",
                inputs=[
                    StructureNode(
                        kind="combine",
                        operator=CombineOp.INTERSECT,
                        inputs=[
                            StructureNode(
                                kind="transform",
                                criterion_id="step_f319e55c",
                                inputs=[_leaf("step_e97903fe")],
                            ),
                            _leaf("step_54ce1477"),
                        ],
                    )
                ],
            )
        ),
    )


def _held(stated: Constraint, spec: OperationalSpec) -> SiteCheck:
    tree = structure_criteria(spec.structure)
    classes = {c.record_class for c in spec.criteria if c.id in tree and c.record_class}
    return record_type_check(stated, spec.record_type, classes)


def _record_type_requirement(
    record_class: str, label: str, role: RecordRole = "answer"
) -> Constraint:
    return Constraint(
        kind=ConstraintKind.RECORD_TYPE,
        label=label,
        requested_value=label,
        source=ConstraintSource.USER_EXPLICIT,
        value=RecordTypeValue(record_class=record_class, role=role),
    )


def _groups_without_mammals() -> OperationalSpec:
    return OperationalSpec(
        criteria=[
            _criterion("step_ca4b3c03", _PATTERN, "group"),
            _criterion("step_35d2c9ab", "ByTaxonomy", "sequence"),
            _criterion("step_groups_of", "GroupsFromSequences", "group"),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(
                        kind="transform",
                        criterion_id="step_groups_of",
                        inputs=[_leaf("step_35d2c9ab")],
                    ),
                    _leaf("step_ca4b3c03"),
                ],
            )
        ),
    )


def test_ortholog_groups_are_met_on_the_group_class() -> None:
    check = _held(_record_type_requirement("group", "ortholog groups"), _pattern_spec())

    assert (check.status, check.evidence) == (
        "pass",
        "the result step returns group records",
    )


def test_proteins_passed_through_are_met_on_the_group_class() -> None:
    check = _held(
        _record_type_requirement("sequence", "protein records", "through"),
        _kinase_spec(),
    )

    assert (check.status, check.evidence) == (
        "pass",
        "a step of the strategy returns sequence",
    )


def test_a_record_type_as_the_answer_is_compared_with_the_root() -> None:
    check = _held(
        _record_type_requirement("sequence", "protein records"), _kinase_spec()
    )

    assert (check.status, check.evidence) == (
        "fail",
        "the result step returns group records",
    )


def test_proteins_asked_as_the_answer_fail_on_a_root_one_transform_short() -> None:
    stated = _record_type_requirement("sequence", "record type")
    check = _held(stated, _groups_without_mammals())

    assert (check.status, check.requirement) == ("fail", stated.id)


def test_a_class_passed_through_only_outside_the_tree_fails() -> None:
    spec = _pattern_spec()
    spec.criteria.append(_criterion("step_dropped", "ByTaxonomy", "sequence"))

    check = _held(
        _record_type_requirement("sequence", "protein records", "through"), spec
    )

    assert (check.status, check.evidence) == (
        "fail",
        "no step of the strategy returns these records",
    )


def test_ortholog_groups_on_the_protein_class_fail() -> None:
    spec = OperationalSpec(
        criteria=[_criterion("step_ids", "ByIdList", "sequence")],
        structure=SpecStructure(root=_leaf("step_ids")),
    )

    check = _held(_record_type_requirement("group", "ortholog groups"), spec)

    assert (check.status, check.evidence) == (
        "fail",
        "the result step returns sequence records",
    )


def test_genes_on_a_group_strategy_with_no_gene_step_fail() -> None:
    check = _held(_record_type_requirement("gene", "genes"), _pattern_spec())

    assert (check.status, check.evidence) == (
        "fail",
        "the result step returns group records",
    )
