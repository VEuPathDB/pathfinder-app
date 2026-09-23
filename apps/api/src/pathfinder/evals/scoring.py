"""The structural signature of a strategy, and the difference report of one case.

The signature drops step ids and parameter values, so two builds of the same
shape compare equal. A failing case reports every difference it found, each
naming the field, the expectation and what the run produced, and carries the
graded distance beside the verdict.
"""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, fold, walk

from pathfinder.evals.case import EvalCase
from pathfinder.evals.distance import (
    ComparisonNode,
    StrategyDistance,
    strategy_distance,
    tree_from_signature,
)

NO_STRATEGY = "(none)"


def _node_signature(node: StrategyStepNode, inputs: list[str]) -> str:
    kind = node.infer_kind()
    slots = [*inputs, "?", "?"]
    if kind == "combine":
        operator = node.operator.value if node.operator else "?"
        return f"({slots[0]} {operator} {slots[1]})"
    if kind == "transform":
        return f"{node.search_name}({slots[0]})"
    return node.search_name


def structure_signature(ast: StrategyAst) -> str:
    """The shape of *ast* as one string: search names and operators, no ids."""
    return fold(ast.root, _node_signature)


def step_titles(ast: StrategyAst) -> list[str]:
    """The title of every step that runs a search, combines left out."""
    nodes = [*walk(ast.root)]
    for detached in ast.detached_roots:
        nodes.extend(walk(detached))
    return [node.display_label for node in nodes if node.infer_kind() != "combine"]


class ObservedOutcome(CamelModel):
    """What one run of a case produced."""

    model_config = ConfigDict(frozen=True)

    built_strategy: bool
    structure: str | None = None
    record_type: str | None = None
    step_count: int | None = None
    verified: bool | None = None
    step_ids_unchanged: bool | None = None
    tree: ComparisonNode | None = None
    step_titles: list[str] = Field(default_factory=list)
    reply_text: str = ""


class CaseDifference(CamelModel):
    """One named disagreement between the expectation and the run."""

    model_config = ConfigDict(frozen=True)

    field: str
    expected: str
    actual: str


class CaseScore(CamelModel):
    """The verdict on one case, the differences behind it, and how far off it is."""

    model_config = ConfigDict(frozen=True)

    name: str
    passed: bool
    differences: list[CaseDifference] = Field(default_factory=list)
    distance: StrategyDistance | None = None


def _build_difference(
    case: EvalCase,
    observed: ObservedOutcome,
) -> CaseDifference | None:
    expected = case.expected.builds_strategy
    if expected is None or expected == observed.built_strategy:
        return None
    return CaseDifference(
        field="builtStrategy",
        expected=str(case.expected.builds_strategy).lower(),
        actual=observed.structure or str(observed.built_strategy).lower(),
    )


def _value_differences(
    case: EvalCase,
    observed: ObservedOutcome,
) -> list[CaseDifference]:
    expected = case.expected
    compared: tuple[tuple[str, object | None, object | None], ...] = (
        ("structure", expected.structure, observed.structure or NO_STRATEGY),
        ("recordType", expected.record_type, observed.record_type),
        ("stepCount", expected.step_count, observed.step_count),
        ("verified", expected.verified, observed.verified),
        (
            "stepIdsUnchanged",
            expected.step_ids_unchanged,
            observed.step_ids_unchanged,
        ),
    )
    return [
        CaseDifference(field=field, expected=str(want), actual=str(got))
        for field, want, got in compared
        if want is not None and want != got
    ]


def _phrase_differences(
    case: EvalCase,
    observed: ObservedOutcome,
) -> list[CaseDifference]:
    reply = observed.reply_text.casefold()
    missing = [p for p in case.expected.reply_mentions if p.casefold() not in reply]
    present = [p for p in case.expected.reply_omits if p.casefold() in reply]
    differences: list[CaseDifference] = []
    if missing:
        differences.append(
            CaseDifference(
                field="replyMentions",
                expected=", ".join(missing),
                actual=observed.reply_text[:200],
            ),
        )
    if present:
        differences.append(
            CaseDifference(
                field="replyOmits",
                expected=", ".join(present),
                actual=observed.reply_text[:200],
            ),
        )
    return differences


def _title_differences(
    case: EvalCase,
    observed: ObservedOutcome,
) -> list[CaseDifference]:
    """The reply names what runs, and no step is titled by the forbidden words."""
    reply = observed.reply_text.casefold()
    differences: list[CaseDifference] = []
    if case.expected.reply_names_its_searches:
        unnamed = [t for t in observed.step_titles if t.casefold() not in reply]
        if unnamed or (not observed.built_strategy and "?" not in reply):
            differences.append(
                CaseDifference(
                    field="replyNamesItsSearches",
                    expected=", ".join(unnamed) or "a question",
                    actual=observed.reply_text[:200],
                ),
            )
    titled = [
        title
        for title in observed.step_titles
        for phrase in case.expected.step_titles_omit
        if phrase.casefold() in title.casefold()
    ]
    if titled:
        differences.append(
            CaseDifference(
                field="stepTitlesOmit",
                expected=", ".join(case.expected.step_titles_omit),
                actual=", ".join(titled),
            ),
        )
    return differences


def _expected_tree(case: EvalCase) -> ComparisonNode | None:
    """The shape the case states, carrying the parameters it names."""
    if case.expected.structure is None:
        return None
    return _with_parameters(
        tree_from_signature(case.expected.structure),
        case.expected.parameters,
    )


def _with_parameters(
    node: ComparisonNode,
    by_search: dict[str, dict[str, str]],
) -> ComparisonNode:
    return node.model_copy(
        update={
            "parameters": dict(by_search.get(node.search_name, {})),
            "children": tuple(
                _with_parameters(child, by_search) for child in node.children
            ),
        },
    )


def _parameter_differences(
    case: EvalCase,
    observed: ObservedOutcome,
) -> list[CaseDifference]:
    """One difference per named parameter the produced strategy disagrees on."""
    if not case.expected.parameters or observed.tree is None:
        return []
    produced = _parameters_by_search(observed.tree)
    differences: list[CaseDifference] = []
    for search, wanted in sorted(case.expected.parameters.items()):
        carried = produced.get(search)
        for name, value in sorted(wanted.items()):
            got = (
                "(no such search)" if carried is None else carried.get(name, "(unset)")
            )
            if got != value:
                differences.append(
                    CaseDifference(
                        field=f"parameters.{search}.{name}",
                        expected=value,
                        actual=got,
                    ),
                )
    return differences


def _parameters_by_search(node: ComparisonNode) -> dict[str, dict[str, str]]:
    carried = {node.search_name: dict(node.parameters)} if node.parameters else {}
    for child in node.children:
        carried.update(_parameters_by_search(child))
    return carried


def _distance(case: EvalCase, observed: ObservedOutcome) -> StrategyDistance | None:
    wanted = _expected_tree(case)
    if wanted is None or observed.tree is None:
        return None
    return strategy_distance(wanted, observed.tree)


def score_case(case: EvalCase, observed: ObservedOutcome) -> CaseScore:
    """Compare one run against its case. Every difference is reported."""
    distance = _distance(case, observed)
    build = _build_difference(case, observed)
    if build is not None:
        return CaseScore(
            name=case.name,
            passed=False,
            differences=[build],
            distance=distance,
        )
    differences = (
        _value_differences(case, observed)
        + _parameter_differences(case, observed)
        + _phrase_differences(case, observed)
        + _title_differences(case, observed)
    )
    return CaseScore(
        name=case.name,
        passed=not differences,
        differences=differences,
        distance=distance,
    )


__all__ = [
    "NO_STRATEGY",
    "CaseDifference",
    "CaseScore",
    "ObservedOutcome",
    "score_case",
    "step_titles",
    "structure_signature",
]
