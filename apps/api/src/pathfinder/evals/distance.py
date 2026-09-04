"""How far apart two strategy shapes are, in four numbers.

A boolean verdict answers "same shape or not", which reads one failure and
draws no trend. The decomposition here answers "how far", so an operator swap
and a strategy that shares no search stop reporting the same thing.

The layers are the ones the retired thesis metric used: topology alone, then
search selection, then the labelled distance that also weighs operators and
parameters, then parameter fidelity over the nodes the two trees share. The
tree distances are Zhang-Shasha, written here in plain Python: the API image
carries no ``zss``, no ``numpy`` and no ``scipy``, and one eval comparison does
not justify three.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field

from pathfinder.domain.strategy.ast import StrategyStepNode
from pathfinder.domain.strategy.strategy_ast import StrategyAst
from pathfinder.domain.strategy.tree import fold

COMBINE_LABEL = "COMBINE"
_ANY_LABEL = "*"
_OPERATOR_WEIGHT = 0.3
_PARAMETER_WEIGHT = 0.7


class ComparisonNode(CamelModel):
    """One node of a strategy, as the distance reads it."""

    model_config = ConfigDict(frozen=True)

    search_name: str
    operator: str | None = None
    parameters: dict[str, str] = Field(default_factory=dict)
    children: tuple[ComparisonNode, ...] = ()

    @property
    def is_combine(self) -> bool:
        return self.search_name == COMBINE_LABEL


class StrategyDistance(CamelModel):
    """Four readings of the gap between an expected shape and a produced one.

    ``topology``, ``search_selection`` and ``labelled`` are distances in
    ``[0, 1]`` where 0 means identical. ``parameter_fidelity`` is a similarity
    in ``[0, 1]`` where 1 means every aligned node carries the same values; it
    is ``None`` when no aligned pair states parameters on both sides.
    """

    model_config = ConfigDict(frozen=True)

    topology: float
    search_selection: float
    labelled: float
    parameter_fidelity: float | None = None


class SignatureSyntaxError(Exception):
    """A structure signature the grammar does not accept."""


def _rounded(value: float) -> float:
    return round(value, 4)


def tree_from_ast(ast: StrategyAst) -> ComparisonNode:
    """The comparison tree of a built strategy, parameters included."""
    return fold(ast.root, _node_from_step)


def _node_from_step(
    step: StrategyStepNode, inputs: list[ComparisonNode]
) -> ComparisonNode:
    return ComparisonNode(
        search_name=(
            COMBINE_LABEL if step.infer_kind() == "combine" else step.search_name
        ),
        operator=step.operator.value if step.operator is not None else None,
        parameters={
            name: _canonical(value.model_dump(mode="json"))
            for name, value in step.parameters.items()
        },
        children=tuple(inputs),
    )


def _canonical(dumped: object) -> str:
    """One comparable text for a parameter value, order-independent."""
    match dumped:
        case {"values": [*items]}:
            return ",".join(sorted(str(item) for item in items))
        case {"value": value}:
            return str(value)
        case [*items]:
            return ",".join(sorted(str(item) for item in items))
        case _:
            return str(dumped)


def tree_from_signature(signature: str) -> ComparisonNode:
    """The comparison tree a structure signature describes, without parameters.

    The grammar is the one ``structure_signature`` writes: ``Name``,
    ``Name(inner)`` and ``(left OPERATOR right)``.
    """
    node, rest = _parse(signature.strip())
    if rest.strip():
        msg = f"trailing text {rest.strip()!r} in signature {signature!r}"
        raise SignatureSyntaxError(msg)
    return node


def _parse(text: str) -> tuple[ComparisonNode, str]:
    if text.startswith("("):
        return _parse_combine(text)
    return _parse_named(text)


def _parse_combine(text: str) -> tuple[ComparisonNode, str]:
    left, rest = _parse(text[1:].lstrip())
    operator, rest = _take_word(rest.lstrip())
    if not operator:
        msg = f"a combine states an operator: {text!r}"
        raise SignatureSyntaxError(msg)
    right, rest = _parse(rest.lstrip())
    rest = rest.lstrip()
    if not rest.startswith(")"):
        msg = f"unclosed combine in {text!r}"
        raise SignatureSyntaxError(msg)
    return (
        ComparisonNode(
            search_name=COMBINE_LABEL,
            operator=operator,
            children=(left, right),
        ),
        rest[1:],
    )


def _parse_named(text: str) -> tuple[ComparisonNode, str]:
    name, rest = _take_word(text)
    if not name:
        msg = f"a search name was expected in {text!r}"
        raise SignatureSyntaxError(msg)
    if rest.startswith("("):
        inner, rest = _parse(rest[1:].lstrip())
        rest = rest.lstrip()
        if not rest.startswith(")"):
            msg = f"unclosed transform in {text!r}"
            raise SignatureSyntaxError(msg)
        return ComparisonNode(search_name=name, children=(inner,)), rest[1:]
    return ComparisonNode(search_name=name), rest


def _take_word(text: str) -> tuple[str, str]:
    index = 0
    while index < len(text) and text[index] not in "()? \t":
        index += 1
    return text[:index], text[index:]


def _postorder(root: ComparisonNode) -> tuple[list[ComparisonNode], list[int]]:
    """Every node in postorder, beside the index of its leftmost descendant."""
    nodes: list[ComparisonNode] = []
    leftmost: list[int] = []

    def visit(node: ComparisonNode) -> int:
        first = len(nodes)
        for child in node.children:
            child_leftmost = visit(child)
            first = min(first, child_leftmost)
        nodes.append(node)
        leftmost.append(first if node.children else len(nodes) - 1)
        return leftmost[-1]

    visit(root)
    return nodes, leftmost


def _keyroots(leftmost: list[int]) -> list[int]:
    """The rightmost node of each distinct leftmost descendant."""
    return sorted({left: index for index, left in enumerate(leftmost)}.values())


type LabelCost = Callable[[ComparisonNode, ComparisonNode], float]


@dataclass(frozen=True, slots=True)
class _Forest:
    """One Zhang-Shasha run: both postorders, the cost, and the table so far."""

    a_nodes: list[ComparisonNode]
    a_left: list[int]
    b_nodes: list[ComparisonNode]
    b_left: list[int]
    treedist: list[list[float]]
    cost: LabelCost

    def fill(self, i: int, j: int) -> None:
        li, lj = self.a_left[i], self.b_left[j]
        rows, columns = i - li + 2, j - lj + 2
        forest = [[0.0] * columns for _ in range(rows)]
        for x in range(1, rows):
            forest[x][0] = forest[x - 1][0] + 1.0
        for y in range(1, columns):
            forest[0][y] = forest[0][y - 1] + 1.0
        for x in range(1, rows):
            for y in range(1, columns):
                a_index, b_index = li + x - 1, lj + y - 1
                deleted = forest[x - 1][y] + 1.0
                inserted = forest[x][y - 1] + 1.0
                if self.a_left[a_index] == li and self.b_left[b_index] == lj:
                    renamed = forest[x - 1][y - 1] + self.cost(
                        self.a_nodes[a_index], self.b_nodes[b_index]
                    )
                    forest[x][y] = min(deleted, inserted, renamed)
                    self.treedist[a_index][b_index] = forest[x][y]
                else:
                    joined = (
                        forest[self.a_left[a_index] - li][self.b_left[b_index] - lj]
                        + self.treedist[a_index][b_index]
                    )
                    forest[x][y] = min(deleted, inserted, joined)


def _tree_edit_distance(
    left: ComparisonNode,
    right: ComparisonNode,
    cost: LabelCost,
) -> float:
    """The Zhang-Shasha distance, with insert and delete costing one each."""
    a_nodes, a_left = _postorder(left)
    b_nodes, b_left = _postorder(right)
    run = _Forest(
        a_nodes=a_nodes,
        a_left=a_left,
        b_nodes=b_nodes,
        b_left=b_left,
        treedist=[[0.0] * len(b_nodes) for _ in a_nodes],
        cost=cost,
    )
    for i in _keyroots(a_left):
        for j in _keyroots(b_left):
            run.fill(i, j)
    return run.treedist[-1][-1]


def _normalized(
    left: ComparisonNode,
    right: ComparisonNode,
    cost: LabelCost,
) -> float:
    size = max(len(_postorder(left)[0]), len(_postorder(right)[0]))
    if size == 0:
        return 0.0
    return _tree_edit_distance(left, right, cost) / size


def _topology_cost(left: ComparisonNode, right: ComparisonNode) -> float:
    del left, right
    return 0.0


def _labelled_cost(left: ComparisonNode, right: ComparisonNode) -> float:
    if left.search_name != right.search_name:
        return 1.0
    cost = _OPERATOR_WEIGHT if left.operator != right.operator else 0.0
    cost += (1.0 - _parameter_similarity(left, right)) * _PARAMETER_WEIGHT
    return min(cost, 1.0)


def _parameter_similarity(left: ComparisonNode, right: ComparisonNode) -> float:
    """Agreement over the parameter names both nodes state.

    A side that states none says nothing about parameters, so the pair carries
    no parameter penalty. Two sides that state values and share no name do
    disagree, and score zero.
    """
    if not left.parameters or not right.parameters:
        return 1.0
    shared = set(left.parameters) & set(right.parameters)
    if not shared:
        return 0.0
    agreed = sum(
        1 for name in shared if left.parameters[name] == right.parameters[name]
    )
    return agreed / len(shared)


def search_names(root: ComparisonNode) -> list[str]:
    """Every search a tree selects, combines excluded, in postorder."""
    nodes, _ = _postorder(root)
    return [node.search_name for node in nodes if not node.is_combine]


def _jaccard_distance(left: ComparisonNode, right: ComparisonNode) -> float:
    a, b = set(search_names(left)), set(search_names(right))
    if not a and not b:
        return 0.0
    return 1.0 - len(a & b) / len(a | b)


def _aligned_pairs(
    left: ComparisonNode,
    right: ComparisonNode,
) -> list[tuple[ComparisonNode, ComparisonNode]]:
    """Search nodes paired by name, in postorder. A name pairs as often as it
    appears on both sides, which is the largest number of pairs a name-only
    alignment can produce."""
    remaining: dict[str, list[ComparisonNode]] = {}
    for node in _postorder(right)[0]:
        if not node.is_combine:
            remaining.setdefault(node.search_name, []).append(node)
    pairs: list[tuple[ComparisonNode, ComparisonNode]] = []
    for node in _postorder(left)[0]:
        candidates = remaining.get(node.search_name)
        if node.is_combine or not candidates:
            continue
        pairs.append((node, candidates.pop(0)))
    return pairs


def parameter_fidelity(
    left: ComparisonNode,
    right: ComparisonNode,
) -> float | None:
    """The mean parameter agreement over aligned searches, or None.

    A pair states nothing on one side, so it says nothing about fidelity and
    does not count.
    """
    scored = [
        _parameter_similarity(a, b)
        for a, b in _aligned_pairs(left, right)
        if a.parameters and b.parameters
    ]
    if not scored:
        return None
    return sum(scored) / len(scored)


def strategy_distance(
    expected: ComparisonNode,
    produced: ComparisonNode,
) -> StrategyDistance:
    """The four-layer reading of how far ``produced`` is from ``expected``."""
    fidelity = parameter_fidelity(expected, produced)
    return StrategyDistance(
        topology=_rounded(_normalized(expected, produced, _topology_cost)),
        search_selection=_rounded(_jaccard_distance(expected, produced)),
        labelled=_rounded(_normalized(expected, produced, _labelled_cost)),
        parameter_fidelity=None if fidelity is None else _rounded(fidelity),
    )


__all__ = [
    "COMBINE_LABEL",
    "ComparisonNode",
    "SignatureSyntaxError",
    "StrategyDistance",
    "parameter_fidelity",
    "search_names",
    "strategy_distance",
    "tree_from_ast",
    "tree_from_signature",
]
