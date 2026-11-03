from __future__ import annotations

from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.operator_questions import operator_questions
from pathfinder.domain.strategy.operator_reading import (
    askable_branches,
    chains,
    operator_source,
    reading_of,
    settled,
    with_operator,
    with_readings,
)
from pathfinder.domain.strategy.operator_reads import OperatorReading
from pathfinder.domain.strategy.question_options import SetOperator

_FLOOR = 0.5


def _stated(
    rid: str, quote: str, kind: ConstraintKind = ConstraintKind.UNTYPED
) -> Constraint:
    return Constraint(
        id=rid,
        kind=kind,
        requested_value=quote,
        label=quote,
        source=ConstraintSource.USER_EXPLICIT,
        quote=quote,
    )


_KINASE = _stated("r_kinase", "kinases")
_GAMETOCYTE = _stated("r_gam", "expressed in gametocytes")
_SECRETED = _stated("r_sec", "secreted")
_ORGANISM = _stated("r_org", "P. falciparum 3D7", ConstraintKind.ORGANISM)
_ASSUMED = Constraint(
    id="r_assumed",
    kind=ConstraintKind.UNTYPED,
    requested_value="drug target",
    label="drug target",
)


def _criterion(cid: str, *linked: Constraint) -> Criterion:
    return Criterion(
        id=cid,
        text=cid,
        search_name=f"GenesBy{cid}",
        answers=[RequirementLink(requirement=c.id) for c in (*linked, _ORGANISM)],
    )


def _leaf(cid: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=cid)


def _combine(op: CombineOp, *inputs: StructureNode) -> StructureNode:
    return StructureNode(kind="combine", operator=op, inputs=list(inputs))


def _spec(root: StructureNode, *criteria: Criterion) -> OperationalSpec:
    return OperationalSpec(criteria=list(criteria), structure=SpecStructure(root=root))


_TWO = _spec(
    _combine(CombineOp.UNION, _leaf("c_kin"), _leaf("c_gam")),
    _criterion("c_kin", _KINASE),
    _criterion("c_gam", _GAMETOCYTE),
)
_HELD = [_KINASE, _GAMETOCYTE, _SECRETED, _ORGANISM, _ASSUMED]


def test_a_chain_of_one_operator_is_one_combine() -> None:
    root = _combine(
        CombineOp.INTERSECT,
        _combine(CombineOp.INTERSECT, _leaf("a"), _leaf("b")),
        _combine(CombineOp.UNION, _leaf("c"), _leaf("d")),
    )

    found = chains(SpecStructure(root=root))

    assert [
        (c.head.operator, [sorted(o.criterion_id or "+" for o in c.operands)])
        for c in found
    ] == [
        (CombineOp.INTERSECT, [["+", "a", "b"]]),
        (CombineOp.UNION, [["c", "d"]]),
    ]


def test_a_combine_is_asked_only_when_each_branch_links_a_stated_quote() -> None:
    assumed = _spec(
        _combine(CombineOp.INTERSECT, _leaf("c_kin"), _leaf("c_drug")),
        _criterion("c_kin", _KINASE),
        _criterion("c_drug", _ASSUMED),
    )

    assert (
        [b.quotes for b in askable_branches(_TWO, _HELD)],
        askable_branches(assumed, _HELD),
    ) == ([(("kinases",), ("expressed in gametocytes",))], [])


def test_a_requirement_every_branch_links_is_no_branch_s_quote() -> None:
    [branches] = askable_branches(_TWO, _HELD)

    assert branches.ids == (("r_kinase",), ("r_gam",))


def test_a_confident_other_operator_disagrees() -> None:
    [chain] = chains(_TWO.structure)

    readings = [
        reading_of(chain, choice, confidence, _FLOOR, (("r_kinase",), ("r_gam",)))
        for choice, confidence in (
            ("intersect", 0.91),
            ("union", 0.88),
            ("intersect", 0.42),
            ("not_stated", 0.95),
            ("not_combined_directly", 0.9),
            ("right_minus_left", 0.8),
        )
    ]

    assert [(r.read, r.read_operator) for r in readings] == [
        ("disagrees", CombineOp.INTERSECT),
        ("agrees", CombineOp.UNION),
        ("unsure", CombineOp.INTERSECT),
        ("not_stated", None),
        ("not_stated", None),
        ("disagrees", CombineOp.RMINUS),
    ]


def _disagreeing(spec: OperationalSpec) -> OperationalSpec:
    [chain] = chains(spec.structure)
    return with_readings(
        spec,
        [reading_of(chain, "intersect", 0.91, _FLOOR, (("r_kinase",), ("r_gam",)))],
    )


def test_an_open_disagreement_holds_the_build() -> None:
    assert (_TWO.ready_to_build, _disagreeing(_TWO).ready_to_build) == (True, False)


def test_a_picked_operator_rewrites_the_chain_and_is_the_researcher_s() -> None:
    picked = with_operator(_disagreeing(_TWO), ["c_gam", "c_kin"], CombineOp.INTERSECT)

    assert picked.structure is not None
    assert (
        picked.structure.root.operator,
        [(r.read, r.built) for r in picked.operator_reads],
        operator_source(picked, frozenset({"c_kin", "c_gam"})),
    ) == (CombineOp.INTERSECT, [("picked", CombineOp.INTERSECT)], "card")


def test_a_pick_survives_a_new_read() -> None:
    picked = with_operator(_disagreeing(_TWO), ["c_gam", "c_kin"], CombineOp.INTERSECT)
    [chain] = chains(picked.structure)

    reread = with_readings(
        picked, [reading_of(chain, "union", 0.9, _FLOOR, (("r_kinase",), ("r_gam",)))]
    )

    assert [r.read for r in reread.operator_reads] == ["picked"]


def test_who_chose_a_combine() -> None:
    [chain] = chains(_TWO.structure)
    agreed = with_readings(
        _TWO, [reading_of(chain, "union", 0.9, _FLOOR, (("r_kinase",), ("r_gam",)))]
    )
    unsure = with_readings(
        _TWO, [reading_of(chain, "union", 0.2, _FLOOR, (("r_kinase",), ("r_gam",)))]
    )
    both = frozenset({"c_kin", "c_gam"})

    assert (
        operator_source(agreed, both),
        operator_source(unsure, both),
        operator_source(_TWO, both),
        operator_source(_TWO, frozenset({"c_kin", "elsewhere"})),
    ) == ("stated", "chosen", "chosen", None)


def test_a_disagreement_the_card_does_not_ask_is_the_assistant_s() -> None:
    kept = settled(_disagreeing(_TWO), asked=[])

    assert ([r.read for r in kept.operator_reads], kept.ready_to_build) == (
        ["unsure"],
        True,
    )


def test_a_reading_of_another_tree_reads_nothing() -> None:
    reading = OperatorReading(
        criteria=["c_gam", "c_kin"], built=CombineOp.INTERSECT, read="disagrees"
    )
    spec = _TWO.model_copy(update={"operator_reads": [reading]})

    assert operator_source(spec, frozenset({"c_kin", "c_gam"})) == "chosen"


def test_a_disagreement_asks_the_built_and_the_read_operator() -> None:
    [question] = operator_questions(_disagreeing(_TWO), _HELD, noun="gene")

    assert (
        question.question,
        [(o.label, o.binding) for o in question.options],
        question.requirement_ids,
    ) == (
        (
            'Your words read as genes in both "kinases" and "expressed in '
            'gametocytes", but the plan finds genes in "kinases" or "expressed in '
            'gametocytes". Which should it find?'
        ),
        [
            (
                'Keep genes in "kinases" or "expressed in gametocytes"',
                SetOperator(criteria=["c_gam", "c_kin"], operator=CombineOp.UNION),
            ),
            (
                'Change to genes in both "kinases" and "expressed in gametocytes"',
                SetOperator(criteria=["c_gam", "c_kin"], operator=CombineOp.INTERSECT),
            ),
        ],
        ["r_kinase", "r_gam"],
    )


def test_only_a_disagreement_is_asked() -> None:
    [chain] = chains(_TWO.structure)
    agreed = with_readings(
        _TWO, [reading_of(chain, "union", 0.9, _FLOOR, (("r_kinase",), ("r_gam",)))]
    )

    assert operator_questions(agreed, _HELD, noun="gene") == []


def test_a_subtraction_names_the_side_it_removes() -> None:
    [chain] = chains(_TWO.structure)
    minus = with_readings(
        _TWO,
        [
            reading_of(
                chain, "right_minus_left", 0.9, _FLOOR, (("r_kinase",), ("r_gam",))
            )
        ],
    )

    [question] = operator_questions(minus, _HELD, noun="gene")

    assert question.options[1].label == (
        'Change to genes in "expressed in gametocytes" but not in "kinases"'
    )
