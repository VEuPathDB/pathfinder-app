from collections.abc import Mapping
from typing import NamedTuple

from pydantic import ConfigDict
from veupathdb.domain.strategy import (
    CombineOp,
    StepKind,
    StrategyStep,
    StrategyStepNode,
    record_class_of,
    walk,
)
from veupathdb.model import CamelModel


class SearchRecordClasses(CamelModel):
    """The record class a search returns and the classes its input step may
    hold, as WDK declares them; ``takes`` is empty for a search with no input."""

    model_config = ConfigDict(frozen=True)

    display_name: str
    returns: str
    takes: tuple[str, ...] = ()


def _class_view(
    root: StrategyStepNode, own: Mapping[str, str]
) -> dict[str, StrategyStep]:
    return {
        node.id: StrategyStep(
            id=node.id,
            kind=StepKind.COMBINE,
            record_class=own.get(node.id),
            primary_input_id=node.primary_input_id if node.secondary_input else None,
            secondary_input_id=node.secondary_input_id,
        )
        for node in walk(root)
    }


def step_class_of(steps: Mapping[str, StrategyStep], step_id: str) -> str | None:
    view = {
        sid: step
        if step.kind is StepKind.COMBINE
        else step.model_copy(update={"primary_input_id": None})
        for sid, step in steps.items()
    }
    return record_class_of(step_id, view, fallback="") or None


class MixedCombine(NamedTuple):
    operator: CombineOp
    left: StrategyStepNode
    right: StrategyStepNode
    primary: str
    secondary: str


def first_mixed_combine(
    root: StrategyStepNode, own: Mapping[str, str]
) -> MixedCombine | None:
    view = _class_view(root, own)
    for node in walk(root):
        left, right, operator = node.primary_input, node.secondary_input, node.operator
        if left is None or right is None or operator is None:
            continue
        if operator is CombineOp.COLOCATE:
            continue
        primary = record_class_of(left.id, view, fallback="")
        secondary = record_class_of(right.id, view, fallback="")
        if primary and secondary and primary != secondary:
            return MixedCombine(operator, left, right, primary, secondary)
    return None


def _side(node: StrategyStepNode) -> str:
    left, right, operator = node.primary_input, node.secondary_input, node.operator
    if left is None or right is None or operator is None:
        return node.display_name or node.id
    return f"({_side(left)} {operator.value} {_side(right)})"


def mixed_combine_refusal(
    mixed: MixedCombine,
    record_names: Mapping[str, str],
    transforms: Mapping[str, SearchRecordClasses],
) -> str:
    left, right = _side(mixed.left), _side(mixed.right)
    first = record_names.get(mixed.primary, mixed.primary)
    second = record_names.get(mixed.secondary, mixed.secondary)
    named = {mixed.primary: first, mixed.secondary: second}
    remedies = [
        f"{t.display_name} ({name}) maps {named[source]} to {named[target]}: "
        f"put it over {side}."
        for source, target, side in (
            (mixed.primary, mixed.secondary, left),
            (mixed.secondary, mixed.primary, right),
        )
        for name, t in sorted(transforms.items())
        if source in t.takes and t.returns == target
    ]
    remedy = " ".join(remedies) or (
        f"No transform on this site maps {first} to {second} or {second} to "
        f"{first}. Bind both inputs to searches on one record type, or ask the "
        f"researcher."
    )
    return (
        f"The {mixed.operator.value} of {left} ({first}) and {right} ({second}) "
        f"joins two record types. WDK combines only steps of one record type, so "
        f"the site refuses this combine. {remedy}"
    )


def transform_input_refusal(
    root: StrategyStepNode,
    own: Mapping[str, str],
    transforms: Mapping[str, SearchRecordClasses],
    record_names: Mapping[str, str],
) -> str | None:
    """Why the first transform whose input returns a record class it does not
    take is refused, or None. An input of unknown class abstains."""
    view = _class_view(root, own)
    for node in walk(root):
        declared = transforms.get(node.search_name)
        source = node.primary_input
        if node.secondary_input is not None or source is None or declared is None:
            continue
        given = record_class_of(source.id, view, fallback="")
        if not declared.takes or not given or given in declared.takes:
            continue
        label = _side(node)
        takes = " or ".join(record_names.get(c, c) for c in declared.takes)
        returns = record_names.get(declared.returns, declared.returns)
        subtree = record_names.get(given, given)
        return (
            f"{label} runs {declared.display_name} ({node.search_name}), which "
            f"takes {takes} as its input step, and the subtree under it returns "
            f"{subtree}. WDK runs a transform only on the record classes it "
            f"declares, so this tree cannot run. {declared.display_name} maps "
            f"{takes} to {returns}; it is not a filter on {subtree}. Drop {label}, "
            f"bind it to a search on {subtree} that states it, or ask the researcher."
        )
    return None
