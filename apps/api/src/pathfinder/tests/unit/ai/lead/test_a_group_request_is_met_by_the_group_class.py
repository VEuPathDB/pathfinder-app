from __future__ import annotations

from collections.abc import Collection, Mapping

import pytest
from veupathdb.domain.strategy import CombineOp
from veupathdb.wdk import WDKRecordType

from pathfinder.ai.lead.verify_review import ReviewRecord, review_held_to_the_turn
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.requirement_reports import RecordRole
from pathfinder.services.strategies import record_classes
from pathfinder.tests._support.orthomcl_record_classes import (
    recorded_orthomcl_record_types,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    requirement,
)

_MOST_PLASMODIUM = (
    "Which ortholog groups are found in at least 90% of the Plasmodium genomes "
    "and in no Toxoplasma gondii genome?"
)
_SINGLE_COPY = "List single-copy ortholog groups across the apicomplexans."
_KINASE_GROUPS = (
    "Take the ortholog groups that contain a protein with the protein kinase "
    "domain PF00069, keep only their Plasmodium falciparum 3D7 proteins, then give "
    "me the ortholog groups those proteins belong to."
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
    text: str,
    stated: Constraint,
    spec: OperationalSpec,
    asked: str,
    class_names: Mapping[str, Collection[str]],
    role: RecordRole | None = None,
) -> RequirementCheck:
    record = ReviewRecord(
        messages=(asked,),
        requirements=(stated,),
        spec=spec,
        read_as=lambda reference: None,
        record_url=lambda gene_id: gene_id,
        class_names=class_names,
        record_roles={} if role is None else {stated.key: role},
    )
    row = RequirementCheck(
        text=text,
        turn=1,
        answered_by=[spec.criteria[0].id],
        how="search",
        status="met",
    )
    return review_held_to_the_turn(
        VerificationReview(requirements=[row]), record
    ).requirements[0]


def _record_type_requirement(value: str, label: str) -> Constraint:
    return requirement(ConstraintKind.RECORD_TYPE, label, value)


def test_the_recorded_ortholog_groups_row_is_met_on_the_group_class(
    class_names: Mapping[str, Collection[str]],
) -> None:
    row = _held(
        "ortholog groups",
        _record_type_requirement("ortholog groups", "ortholog groups"),
        _pattern_spec(),
        _MOST_PLASMODIUM,
        class_names,
    )

    assert (row.status, row.answered_by, row.note) == (
        "met",
        ["step_b08116fe"],
        "the strategy returns groups",
    )


def test_the_recorded_single_copy_row_is_met_on_the_group_class(
    class_names: Mapping[str, Collection[str]],
) -> None:
    row = _held(
        "Single-copy ortholog groups",
        _record_type_requirement(
            "single-copy ortholog groups", "Single-copy ortholog groups"
        ),
        _pattern_spec(),
        _SINGLE_COPY,
        class_names,
    )

    assert (row.status, row.note) == ("met", "the strategy returns groups")


def test_the_recorded_proteins_passed_through_are_met_on_the_group_class(
    class_names: Mapping[str, Collection[str]],
) -> None:
    row = _held(
        "protein records",
        _record_type_requirement("protein", "protein records"),
        _kinase_spec(),
        _KINASE_GROUPS,
        class_names,
        "through",
    )

    assert (row.status, row.answered_by, row.note) == (
        "met",
        ["step_54ce1477", "step_f319e55c"],
        "a step of the strategy returns proteins",
    )


def test_a_plural_row_keeps_the_role_of_the_singular_requirement(
    class_names: Mapping[str, Collection[str]],
) -> None:
    row = _held(
        "proteins",
        _record_type_requirement("protein", "record type"),
        _kinase_spec(),
        _KINASE_GROUPS,
        class_names,
        "through",
    )

    assert (row.status, row.note) == ("met", "a step of the strategy returns proteins")


def test_a_record_type_with_no_role_is_compared_with_the_root(
    class_names: Mapping[str, Collection[str]],
) -> None:
    row = _held(
        "protein records",
        _record_type_requirement("protein", "protein records"),
        _kinase_spec(),
        _KINASE_GROUPS,
        class_names,
    )

    assert (row.status, row.note) == ("unmet", "the strategy returns groups")


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


def test_proteins_asked_as_the_answer_are_unmet_on_a_root_one_transform_short(
    class_names: Mapping[str, Collection[str]],
) -> None:
    row = _held(
        "protein",
        _record_type_requirement("protein", "record type"),
        _groups_without_mammals(),
        "List the Toxoplasma gondii ME49 proteins whose ortholog groups have no "
        "protein from any mammal.",
        class_names,
        "answer",
    )

    assert (row.status, row.answered_by, row.note) == (
        "unmet",
        [],
        "the strategy returns groups",
    )


def test_a_class_passed_through_only_outside_the_tree_is_unmet(
    class_names: Mapping[str, Collection[str]],
) -> None:
    spec = _pattern_spec()
    spec.criteria.append(_criterion("step_dropped", "ByTaxonomy", "sequence"))

    row = _held(
        "protein records",
        _record_type_requirement("protein", "protein records"),
        spec,
        _KINASE_GROUPS,
        class_names,
        "through",
    )

    assert (row.status, row.answered_by, row.note) == (
        "unmet",
        [],
        "no step of the strategy returns protein records",
    )


def test_the_sites_names_decide_which_class_a_row_names(
    class_names: Mapping[str, Collection[str]],
) -> None:
    segments_only = {record_class: [record_class] for record_class in class_names}

    named = [
        _held(
            "protein records",
            _record_type_requirement("protein", "protein records"),
            _kinase_spec(),
            _KINASE_GROUPS,
            names,
            "through",
        ).status
        for names in (class_names, segments_only)
    ]

    assert named == ["met", "unmet"]


def test_proteins_asked_as_the_answer_of_a_group_strategy_are_unmet(
    class_names: Mapping[str, Collection[str]],
) -> None:
    row = _held(
        "proteins",
        _record_type_requirement("proteins", "proteins"),
        _kinase_spec(),
        "Which Plasmodium falciparum 3D7 proteins carry the kinase domain PF00069?",
        class_names,
    )

    assert (row.status, row.answered_by, row.note) == (
        "unmet",
        [],
        "the strategy returns groups",
    )


def test_ortholog_groups_on_the_protein_class_are_unmet(
    class_names: Mapping[str, Collection[str]],
) -> None:
    spec = OperationalSpec(
        criteria=[_criterion("step_ids", "ByIdList", "sequence")],
        structure=SpecStructure(root=_leaf("step_ids")),
    )

    row = _held(
        "ortholog groups",
        _record_type_requirement("ortholog groups", "ortholog groups"),
        spec,
        _MOST_PLASMODIUM,
        class_names,
    )

    assert (row.status, row.note) == ("unmet", "the strategy returns proteins")


def test_genes_on_a_group_strategy_with_no_gene_step_are_unmet(
    class_names: Mapping[str, Collection[str]],
) -> None:
    row = _held(
        "genes",
        _record_type_requirement("genes", "genes"),
        _pattern_spec(),
        _MOST_PLASMODIUM,
        class_names,
    )

    assert (row.status, row.note) == ("unmet", "the strategy returns groups")
