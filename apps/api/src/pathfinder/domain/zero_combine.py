"""A combine that holds no record while each of its inputs holds some, and the
sentence its counts state."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict
from veupathdb.domain.strategy.graph_model import StrategyStep
from veupathdb.domain.strategy.ops import CombineOp


class ZeroCombineCaveat(CamelModel):
    """A combine that holds no record while each input holds some.

    ``inside`` is the input whose records the combine reads against the
    records of ``outside``.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["zero_combine"] = "zero_combine"
    operator: str
    inside: str
    inside_count: int
    outside: str
    outside_count: int
    # True when every record of the inside input is among the outside's.
    all_among: bool
    noun: str = "gene"

    @computed
    def sentence(self) -> str:
        """The operator, and how the records of one input stand to the other's."""
        counted = f"{self.inside_count:,} {self.noun}"
        if self.inside_count != 1:
            counted += "s"
        among = f"among the {self.outside_count:,} of '{self.outside}'"
        if self.inside_count == 1:
            verb = "is" if self.all_among else "is not"
            relation = f"the {counted} of '{self.inside}' {verb} {among}"
        elif self.all_among:
            relation = f"all {counted} of '{self.inside}' are {among}"
        else:
            relation = f"none of the {counted} of '{self.inside}' is {among}"
        return f"{self.operator} holds 0 {self.noun}s: {relation}"

    def texts(self) -> list[str]:
        return [self.inside, self.outside]

    def redacted(self, redact: Callable[[str], str]) -> ZeroCombineCaveat:
        return self.model_copy(
            update={"inside": redact(self.inside), "outside": redact(self.outside)}
        )


# The operators whose empty answer over two inputs that hold records says how
# the inputs stand: the left or the right input wholly inside the other.
_LEFT_INSIDE = frozenset({CombineOp.MINUS, CombineOp.LONLY})
_RIGHT_INSIDE = frozenset({CombineOp.RMINUS, CombineOp.RONLY})


def _zero_combine(
    step: StrategyStep,
    steps: Mapping[str, StrategyStep],
    counts: Mapping[str, int | None],
    noun: str,
) -> ZeroCombineCaveat | None:
    left, right, operator = (
        step.primary_input_id,
        step.secondary_input_id,
        step.operator,
    )
    if operator is None or left is None or right is None:
        return None
    if counts.get(step.id) != 0 or not counts.get(left) or not counts.get(right):
        return None
    named = {sid: (steps[sid].display_label, counts[sid] or 0) for sid in (left, right)}
    if operator in _LEFT_INSIDE:
        inside, outside, all_among = left, right, True
    elif operator in _RIGHT_INSIDE:
        inside, outside, all_among = right, left, True
    elif operator is CombineOp.INTERSECT:
        inside, outside = sorted((left, right), key=lambda sid: named[sid][1])
        all_among = False
    else:
        return None
    return ZeroCombineCaveat(
        operator=operator.value,
        inside=named[inside][0],
        inside_count=named[inside][1],
        outside=named[outside][0],
        outside_count=named[outside][1],
        all_among=all_among,
        noun=noun,
    )


def zero_combine_caveats(
    steps: Mapping[str, StrategyStep], counts: Mapping[str, int | None], noun: str
) -> list[ZeroCombineCaveat]:
    """Each combine of the strategy that holds no record over inputs that do."""
    found = (_zero_combine(step, steps, counts, noun) for step in steps.values())
    return [caveat for caveat in found if caveat is not None]
