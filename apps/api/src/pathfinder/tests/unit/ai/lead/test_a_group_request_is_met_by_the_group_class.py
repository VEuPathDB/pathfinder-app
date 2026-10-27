from __future__ import annotations

from collections.abc import Collection, Mapping

import pytest
from veupathdb.domain.strategy import CombineOp
from veupathdb.wdk import WDKRecordType

from pathfinder.domain.requirement_checks import classes_named, record_type_check
from pathfinder.domain.site_checks import SiteCheck
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    structure_criteria,
)
from pathfinder.domain.strategy.requirement_reports import RecordRole
from pathfinder.services.strategies import record_classes
from pathfinder.tests._support.orthomcl_record_classes import (
    recorded_orthomcl_record_types,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    requirement,
)

_PATTERN = "GroupsByPhyleticPattern"


@pytest.fixture
async def class_names(
    monkeypatch: pytest.MonkeyPatch,
) -> Mapping[str, Collection[str]]:
    async def _record_types(_site_id: str) -> list[WDKRecordType]:
        return recorded_orthomcl_record_types()

    monkeypatch.setattr(record_classes, "get_raw_record_types", _record_types)
    return await record_classes.names_of_every_record_type("orthomcl")


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


def _held(
    stated: Constraint,
    spec: OperationalSpec,
    class_names: Mapping[str, Collection[str]],
    role: RecordRole = "answer",
) -> SiteCheck:
    tree = structure_criteria(spec.structure)
    classes = {c.record_class for c in spec.criteria if c.id in tree and c.record_class}
    return record_type_check(
        stated,
        role,
        classes_named(stated.requested_value, class_names),
        spec.record_type,
        classes,
    )


def _record_type_requirement(value: str, label: str) -> Constraint:
    return requirement(ConstraintKind.RECORD_TYPE, label, value)


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


def test_the_recorded_ortholog_groups_are_met_on_the_group_class(
    class_names: Mapping[str, Collection[str]],
) -> None:
    check = _held(
        _record_type_requirement("ortholog groups", "ortholog groups"),
        _pattern_spec(),
        class_names,
    )

    assert (check.status, check.evidence) == (
        "pass",
        "the result step returns group records",
    )


def test_the_recorded_single_copy_groups_are_met_on_the_group_class(
    class_names: Mapping[str, Collection[str]],
) -> None:
    check = _held(
        _record_type_requirement(
            "single-copy ortholog groups", "Single-copy ortholog groups"
        ),
        _pattern_spec(),
        class_names,
    )

    assert check.status == "pass"


def test_the_recorded_proteins_passed_through_are_met_on_the_group_class(
    class_names: Mapping[str, Collection[str]],
) -> None:
    check = _held(
        _record_type_requirement("protein", "protein records"),
        _kinase_spec(),
        class_names,
        "through",
    )

    assert (check.status, check.evidence) == (
        "pass",
        "a step of the strategy returns sequence",
    )


def test_a_record_type_with_no_role_is_compared_with_the_root(
    class_names: Mapping[str, Collection[str]],
) -> None:
    check = _held(
        _record_type_requirement("protein", "protein records"),
        _kinase_spec(),
        class_names,
    )

    assert (check.status, check.evidence) == (
        "fail",
        "the result step returns group records",
    )


def test_proteins_asked_as_the_answer_fail_on_a_root_one_transform_short(
    class_names: Mapping[str, Collection[str]],
) -> None:
    check = _held(
        _record_type_requirement("protein", "record type"),
        _groups_without_mammals(),
        class_names,
        "answer",
    )

    assert (check.status, check.requirement) == ("fail", "record_type:protein")


def test_a_class_passed_through_only_outside_the_tree_fails(
    class_names: Mapping[str, Collection[str]],
) -> None:
    spec = _pattern_spec()
    spec.criteria.append(_criterion("step_dropped", "ByTaxonomy", "sequence"))

    check = _held(
        _record_type_requirement("protein", "protein records"),
        spec,
        class_names,
        "through",
    )

    assert (check.status, check.evidence) == (
        "fail",
        "no step of the strategy returns these records",
    )


def test_the_sites_names_decide_which_class_a_requirement_names(
    class_names: Mapping[str, Collection[str]],
) -> None:
    segments_only = {record_class: [record_class] for record_class in class_names}

    named = [
        _held(
            _record_type_requirement("protein", "protein records"),
            _kinase_spec(),
            names,
            "through",
        ).status
        for names in (class_names, segments_only)
    ]

    assert named == ["pass", "unchecked"]


def test_ortholog_groups_on_the_protein_class_fail(
    class_names: Mapping[str, Collection[str]],
) -> None:
    spec = OperationalSpec(
        criteria=[_criterion("step_ids", "ByIdList", "sequence")],
        structure=SpecStructure(root=_leaf("step_ids")),
    )

    check = _held(
        _record_type_requirement("ortholog groups", "ortholog groups"),
        spec,
        class_names,
    )

    assert (check.status, check.evidence) == (
        "fail",
        "the result step returns sequence records",
    )


def test_genes_on_a_group_strategy_with_no_gene_step_fail(
    class_names: Mapping[str, Collection[str]],
) -> None:
    check = _held(
        _record_type_requirement("genes", "genes"), _pattern_spec(), class_names
    )

    assert (check.status, check.evidence) == (
        "fail",
        "the result step returns group records",
    )
