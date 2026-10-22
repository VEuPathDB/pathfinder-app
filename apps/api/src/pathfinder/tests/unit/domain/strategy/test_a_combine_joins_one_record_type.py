from __future__ import annotations

from collections.abc import Mapping

import pytest
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    ColocationParams,
    CombineOp,
    StrategyStepNode,
)

from pathfinder.domain.strategy.validate import (
    SearchRecordClasses,
    first_mixed_combine,
    mixed_combine_refusal,
)
from pathfinder.services.strategies.record_classes import record_classes_of
from pathfinder.tests._support.orthomcl_record_classes import (
    FROM_GROUPS,
    PHYLETIC_PATTERN,
    SEQUENCE_BOOLEAN,
)
from pathfinder.tests._support.orthomcl_site import BY_ID_LIST, GROUPS_FROM_SEQUENCES

CLASSES = {
    s.url_segment: record_classes_of(s, s.output_record_class_name)
    for s in (BY_ID_LIST, GROUPS_FROM_SEQUENCES, PHYLETIC_PATTERN, FROM_GROUPS)
}
TRANSFORMS = {
    s.url_segment: record_classes_of(s, s.output_record_class_name)
    for s in (GROUPS_FROM_SEQUENCES, FROM_GROUPS, SEQUENCE_BOOLEAN)
}
NAMES = {"sequence": "Proteins", "group": "Ortholog Groups"}


def _step(
    step_id: str, search_name: str, *inputs: StrategyStepNode
) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id, search_name=search_name, primary_input=next(iter(inputs), None)
    )


def _join(
    op: CombineOp, left: StrategyStepNode, right: StrategyStepNode
) -> StrategyStepNode:
    return StrategyStepNode(
        id="c_join",
        search_name=COMBINE_SEARCH_NAME,
        operator=op,
        primary_input=left,
        secondary_input=right,
        colocation_params=ColocationParams() if op is CombineOp.COLOCATE else None,
    )


def _protein() -> StrategyStepNode:
    return _step("c_tb927_10_10390", "ByIdList")


def _mammal_groups() -> StrategyStepNode:
    return _step("c_mammal_presence", "GroupsByPhyleticPattern")


def _refusal(
    root: StrategyStepNode,
    transforms: Mapping[str, SearchRecordClasses] = TRANSFORMS,
) -> str | None:
    mixed = first_mixed_combine(root, CLASSES)
    if mixed is None:
        return None
    return mixed_combine_refusal(mixed, NAMES, transforms)


def test_a_protein_step_intersected_with_a_group_step_is_refused() -> None:
    root = _join(CombineOp.INTERSECT, _protein(), _mammal_groups())

    assert _refusal(root) == (
        "The INTERSECT of c_tb927_10_10390 (Proteins) and c_mammal_presence "
        "(Ortholog Groups) joins two record types. WDK combines only steps of one "
        "record type, so the site refuses this combine. Transform Proteins to "
        "Groups (GroupsFromSequences) maps Proteins to Ortholog Groups: put it over "
        "c_tb927_10_10390. Transform Groups to Proteins (FromGroups) maps Ortholog "
        "Groups to Proteins: put it over c_mammal_presence."
    )


@pytest.mark.parametrize("op", [CombineOp.UNION, CombineOp.MINUS])
def test_every_boolean_operator_joins_one_record_type(op: CombineOp) -> None:
    mixed = first_mixed_combine(_join(op, _protein(), _mammal_groups()), CLASSES)

    assert mixed is not None
    assert (mixed.operator, mixed.primary, mixed.secondary) == (
        op,
        "sequence",
        "group",
    )


def test_a_site_with_no_transform_between_them_says_so() -> None:
    root = _join(CombineOp.INTERSECT, _protein(), _mammal_groups())

    refusal = _refusal(root, transforms={})

    assert refusal is not None
    assert refusal.endswith(
        "No transform on this site maps Proteins to Ortholog Groups or Ortholog "
        "Groups to Proteins. Bind both inputs to searches on one record type, or "
        "ask the researcher."
    )


def test_a_nested_combine_names_the_inputs_it_joins() -> None:
    proteins = _join(CombineOp.UNION, _protein(), _step("c_other", "ByIdList"))
    root = _join(CombineOp.INTERSECT, proteins, _mammal_groups())

    refusal = _refusal(root)

    assert refusal is not None
    assert refusal.startswith(
        "The INTERSECT of (c_tb927_10_10390 UNION c_other) (Proteins) and "
        "c_mammal_presence (Ortholog Groups) joins two record types."
    )


def test_combines_of_one_record_type_or_an_unknown_one_are_accepted() -> None:
    groups_of_the_protein = _step("c_groups", "GroupsFromSequences", _protein())
    accepted = {
        "two protein steps": _join(
            CombineOp.INTERSECT, _protein(), _step("c_other", "ByIdList")
        ),
        "the protein's groups and the mammal groups": _join(
            CombineOp.INTERSECT, groups_of_the_protein, _mammal_groups()
        ),
        "an input of unknown class": _join(
            CombineOp.INTERSECT, _protein(), _step("c_unread", "Unlisted")
        ),
        "a colocation": _join(CombineOp.COLOCATE, _protein(), _mammal_groups()),
    }

    assert {
        name: first_mixed_combine(root, CLASSES) for name, root in accepted.items()
    } == (dict.fromkeys(accepted))
