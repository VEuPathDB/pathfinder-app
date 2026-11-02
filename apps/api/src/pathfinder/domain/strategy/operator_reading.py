from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Literal, NamedTuple

from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.constraints import (
    STRATEGY_SCOPES,
    Constraint,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    SpecStructure,
    StructureNode,
    criteria_under,
)
from pathfinder.domain.strategy.operator_reads import (
    OperatorRead,
    OperatorReading,
    OperatorSource,
)
from pathfinder.domain.strategy.question_options import SetOperator
from pathfinder.domain.strategy.questions import OpenQuestion

ReadChoice = Literal[
    "intersect",
    "union",
    "left_minus_right",
    "right_minus_left",
    "colocated",
    "not_combined_directly",
    "not_stated",
]

PAIR = 2
OPERATOR_QUESTION = "operator"
_CHAINED = frozenset({CombineOp.INTERSECT, CombineOp.UNION})
_CHOICE_OF: dict[CombineOp, ReadChoice] = {
    CombineOp.INTERSECT: "intersect",
    CombineOp.UNION: "union",
    CombineOp.MINUS: "left_minus_right",
    CombineOp.LONLY: "left_minus_right",
    CombineOp.RMINUS: "right_minus_left",
    CombineOp.RONLY: "right_minus_left",
    CombineOp.COLOCATE: "colocated",
}
OPERATOR_OF: dict[str, CombineOp] = {
    "intersect": CombineOp.INTERSECT,
    "union": CombineOp.UNION,
    "left_minus_right": CombineOp.MINUS,
    "right_minus_left": CombineOp.RMINUS,
    "colocated": CombineOp.COLOCATE,
}


class Chain(NamedTuple):
    head: StructureNode
    members: tuple[StructureNode, ...]
    operands: tuple[StructureNode, ...]

    @property
    def criteria(self) -> frozenset[str]:
        return criteria_under(self.head)


def _collapsed(node: StructureNode) -> tuple[list[StructureNode], list[StructureNode]]:
    if node.operator not in _CHAINED:
        return [node], list(node.inputs)
    members, operands = [node], []
    for child in node.inputs:
        if child.kind == "combine" and child.operator is node.operator:
            inner, under = _collapsed(child)
            members += inner
            operands += under
        else:
            operands.append(child)
    return members, operands


def _chains(node: StructureNode, parent: CombineOp | None) -> Iterator[Chain]:
    joined = node.kind == "combine"
    if joined and not (node.operator in _CHAINED and node.operator is parent):
        members, operands = _collapsed(node)
        yield Chain(head=node, members=tuple(members), operands=tuple(operands))
    for child in node.inputs:
        yield from _chains(child, node.operator if joined else None)


def chains(structure: SpecStructure | None) -> list[Chain]:
    return [] if structure is None else list(_chains(structure.root, None))


class Branches(NamedTuple):
    chain: Chain
    quotes: tuple[tuple[str, ...], ...]
    ids: tuple[tuple[str, ...], ...]


def _linked(spec: OperationalSpec, operand: StructureNode) -> list[str]:
    under = criteria_under(operand)
    return [
        link.requirement for c in spec.criteria if c.id in under for link in c.answers
    ]


def _branches(
    spec: OperationalSpec, chain: Chain, stated: dict[str, Constraint]
) -> Branches | None:
    linked = [dict.fromkeys(_linked(spec, operand)) for operand in chain.operands]
    shared = {rid for rid in stated if sum(rid in ids for ids in linked) > 1}
    own = [
        [rid for rid in ids if rid in stated and rid not in shared] for ids in linked
    ]
    if not all(own):
        return None
    return Branches(
        chain=chain,
        quotes=tuple(tuple(stated[rid].quote for rid in ids) for ids in own),
        ids=tuple(tuple(ids) for ids in own),
    )


def askable_branches(
    spec: OperationalSpec, requirements: Sequence[Constraint]
) -> list[Branches]:
    stated = {
        c.id: c
        for c in requirements
        if c.source is ConstraintSource.USER_EXPLICIT
        and c.quote
        and c.kind not in STRATEGY_SCOPES
    }
    picked = [r for r in spec.operator_reads if r.read == "picked"]
    return [
        found
        for chain in chains(spec.structure)
        if (len(chain.operands) == PAIR or chain.head.operator in _CHAINED)
        and not any(r.reads(chain.criteria, chain.head.operator) for r in picked)
        and (found := _branches(spec, chain, stated)) is not None
    ]


def reading_of(
    chain: Chain,
    choice: str,
    confidence: float,
    floor: float,
    branches: Sequence[Sequence[str]],
) -> OperatorReading:
    built = chain.head.combine_operator
    read_operator = OPERATOR_OF.get(choice)
    read: OperatorRead
    if read_operator is None:
        read = "not_stated"
    elif confidence < floor:
        read = "unsure"
    elif choice == _CHOICE_OF[built]:
        read = "agrees"
    else:
        read = "disagrees"
    return OperatorReading(
        criteria=sorted(chain.criteria),
        built=built,
        read=read,
        read_operator=read_operator,
        confidence=confidence,
        branches=[list(ids) for ids in branches],
    )


def with_readings(
    spec: OperationalSpec, readings: Sequence[OperatorReading]
) -> OperationalSpec:
    picked = [r for r in spec.operator_reads if r.read == "picked"]
    fresh = [
        r
        for r in readings
        if not any(p.reads(frozenset(r.criteria), r.built) for p in picked)
    ]
    return spec.model_copy(update={"operator_reads": [*picked, *fresh]})


def _rewritten(
    node: StructureNode, members: Sequence[StructureNode], operator: CombineOp
) -> StructureNode:
    inputs = [_rewritten(child, members, operator) for child in node.inputs]
    if any(node is member for member in members):
        return node.model_copy(update={"operator": operator, "inputs": inputs})
    return node.model_copy(update={"inputs": inputs})


def with_operator(
    spec: OperationalSpec, criteria: Sequence[str], operator: CombineOp
) -> OperationalSpec:
    wanted = frozenset(criteria)
    chain = next((c for c in chains(spec.structure) if c.criteria == wanted), None)
    if chain is None or spec.structure is None:
        return spec
    asked = next(
        (r for r in spec.operator_reads if frozenset(r.criteria) == wanted), None
    )
    structure = SpecStructure(
        root=_rewritten(spec.structure.root, chain.members, operator)
    )
    picked = OperatorReading(
        criteria=sorted(wanted),
        built=operator,
        read="picked",
        read_operator=operator,
        branches=[] if asked is None else asked.branches,
    )
    kept = [r for r in spec.operator_reads if frozenset(r.criteria) != wanted]
    return spec.model_copy(
        update={"structure": structure, "operator_reads": [*kept, picked]}
    )


def _deepest(node: StructureNode, wanted: frozenset[str]) -> StructureNode | None:
    if node.kind != "combine" or not wanted <= criteria_under(node):
        deeper = (_deepest(child, wanted) for child in node.inputs)
        return next((found for found in deeper if found is not None), None)
    for child in node.inputs:
        found = _deepest(child, wanted)
        if found is not None:
            return found
    return node


def operator_source(
    spec: OperationalSpec, criteria: frozenset[str]
) -> OperatorSource | None:
    if spec.structure is None:
        return None
    node = _deepest(spec.structure.root, criteria)
    chain = next(
        (
            c
            for c in chains(spec.structure)
            if any(node is member for member in c.members)
        ),
        None,
    )
    if chain is None:
        return None
    reading = next(
        (
            r
            for r in spec.held_operator_reads()
            if r.reads(chain.criteria, chain.head.operator)
        ),
        None,
    )
    return "chosen" if reading is None else reading.source


def _asked_criteria(questions: Sequence[OpenQuestion]) -> set[frozenset[str]]:
    asked: set[frozenset[str]] = set()
    for question in questions:
        for option in question.options:
            match option.binding:
                case SetOperator(criteria=criteria):
                    asked.add(frozenset(criteria))
                case _:
                    pass
    return asked


def settled(spec: OperationalSpec, *, asked: Sequence[OpenQuestion]) -> OperationalSpec:
    on_the_card = _asked_criteria(asked)
    return spec.model_copy(
        update={
            "operator_reads": [
                r.model_copy(update={"read": "unsure"})
                if r.read == "disagrees" and frozenset(r.criteria) not in on_the_card
                else r
                for r in spec.operator_reads
            ]
        }
    )


def read_operators(spec: OperationalSpec) -> frozenset[CombineOp]:
    return frozenset(
        r.read_operator
        for r in spec.held_operator_reads()
        if r.read in {"agrees", "disagrees", "picked"} and r.read_operator is not None
    )
