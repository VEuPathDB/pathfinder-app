from __future__ import annotations

from collections.abc import Mapping

import pytest
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    ColocationParams,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
    walk,
)

from pathfinder.domain.strategy.record_class_check import (
    MixedCombine,
    SearchRecordClasses,
    first_mixed_combine,
    mixed_combine_refusal,
    step_class_of,
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


def _own(root: StrategyStepNode) -> dict[str, str]:
    return {
        node.id: CLASSES[node.search_name].returns
        for node in walk(root)
        if node.search_name in CLASSES
    }


def _step(
    step_id: str, search_name: str, *inputs: StrategyStepNode
) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id, search_name=search_name, primary_input=next(iter(inputs), None)
    )


def _join(
    op: CombineOp,
    left: StrategyStepNode,
    right: StrategyStepNode,
    join_id: str = "c_join",
) -> StrategyStepNode:
    return StrategyStepNode(
        id=join_id,
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
    mixed = first_mixed_combine(root, _own(root))
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
    root = _join(op, _protein(), _mammal_groups())

    mixed = first_mixed_combine(root, _own(root))

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
    proteins = _join(
        CombineOp.UNION, _protein(), _step("c_other", "ByIdList"), "c_proteins"
    )
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
        name: first_mixed_combine(root, _own(root)) for name, root in accepted.items()
    } == (dict.fromkeys(accepted))


def test_an_unlisted_transform_never_takes_the_class_of_its_input() -> None:
    unread = _step("c_unread", "Unlisted", _protein())
    root = _join(CombineOp.INTERSECT, unread, _mammal_groups())
    known = _join(CombineOp.INTERSECT, _protein(), _mammal_groups())

    assert [first_mixed_combine(r, _own(r)) for r in (root, known)] == [
        None,
        MixedCombine(
            CombineOp.INTERSECT, _protein(), _mammal_groups(), "sequence", "group"
        ),
    ]


def test_a_colocation_returns_the_class_of_its_primary_input() -> None:
    genes_near_snps = _join(
        CombineOp.COLOCATE,
        _step("c_genes", "GenesByTaxon"),
        _step("c_snps", "SnpsByLocation"),
        "c_near",
    )
    root = _join(
        CombineOp.INTERSECT, genes_near_snps, _step("c_more", "SnpsByLocation")
    )
    own = {"c_genes": "transcript", "c_snps": "snp", "c_more": "snp"}

    mixed = first_mixed_combine(root, own)

    assert mixed is not None
    assert (mixed.left.id, mixed.primary, mixed.secondary) == (
        "c_near",
        "transcript",
        "snp",
    )


def test_a_step_is_named_by_the_name_it_shows() -> None:
    shown = _protein().model_copy(update={"display_name": "Proteins by ID"})
    root = _join(CombineOp.INTERSECT, shown, _mammal_groups())

    refusal = _refusal(root)

    assert refusal is not None
    assert refusal.startswith(
        "The INTERSECT of Proteins by ID (Proteins) and c_mammal_presence "
        "(Ortholog Groups) joins two record types."
    )


def test_a_step_takes_its_own_class_and_a_combine_its_inputs() -> None:
    proteins = _step("c_proteins", "FromGroups", _mammal_groups())
    steps = flatten_tree(
        _join(CombineOp.INTERSECT, proteins, _step("c_taxon", "ByTaxonomy"))
    )
    steps["c_mammal_presence"].record_class = "group"
    steps["c_taxon"].record_class = "sequence"

    assert {sid: step_class_of(steps, sid) for sid in steps} == {
        "c_mammal_presence": "group",
        "c_proteins": None,
        "c_taxon": "sequence",
        "c_join": "sequence",
    }
