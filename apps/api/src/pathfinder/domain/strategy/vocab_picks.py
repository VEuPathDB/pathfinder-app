from __future__ import annotations

from collections.abc import Sequence
from functools import reduce

from pydantic import ConfigDict, Field
from veupathdb.domain.parameters import VocabOption
from veupathdb.model import CamelModel
from veupathdb_mcp.catalog import VocabPick

from pathfinder.domain.strategy.constraint_grounding import dimension_of_parameter
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import SlotQuestion
from pathfinder.domain.strategy.value_binding import pick_terms

_OFFERED = 8


class PickRead(CamelModel):
    model_config = ConfigDict(frozen=True)

    search_name: str
    param_name: str
    requirement: str
    pick: VocabPick
    kept: list[VocabOption] = Field(default_factory=list)

    def note(self) -> str:
        if self.pick.value is None:
            return (
                f"No entry this read kept states {self.requirement!r}, so a "
                "binding of this parameter is asked of the researcher."
            )
        found = (
            f"{self.pick.value} ({self.pick.display}), confidence "
            f"{self.pick.confidence:.2f}"
        )
        if self.pick.settled:
            return (
                f"The entry that states {self.requirement!r} is {found}: bind it "
                "unless the request names another entry."
            )
        return (
            f"The nearest entry to {self.requirement!r} is {found}, which does "
            "not settle it, so a binding of this parameter is asked of the "
            "researcher."
        )

    def _offered(self, bound: BoundValue) -> list[str]:
        return list(
            dict.fromkeys(
                [
                    *([] if self.pick.value is None else [self.pick.value]),
                    *pick_terms(bound.value),
                    *(option.value for option in self.kept),
                ]
            )
        )

    def question(self, criterion: Criterion) -> SlotQuestion:
        named = criterion.display_name_of(self.param_name)
        bound = criterion.resolved_params[self.param_name]
        nearest = (
            "no entry states it surely"
            if self.pick.value is None
            else f"the nearest entry is {self.pick.display}, confidence "
            f"{self.pick.confidence:.2f}"
        )
        return SlotQuestion(
            question=(
                f"Which {named} states {self.requirement!r}? On this site "
                f"{nearest}. Pick an entry, or say in your own words what you mean."
            ),
            dimension=dimension_of_parameter(self.param_name, named),
            recommended_value=self.pick.value or "",
            options=self._offered(bound)[:_OFFERED],
            criterion_id=criterion.id,
            param_name=self.param_name,
            labels={option.value: option.display for option in self.kept},
        )

    def reopened(self, criterion: Criterion) -> Criterion:
        bound = criterion.resolved_params[self.param_name]
        return criterion.model_copy(
            update={
                "resolved_params": {
                    name: value
                    for name, value in criterion.resolved_params.items()
                    if name != self.param_name
                },
                "open_params": [
                    *(
                        s
                        for s in criterion.open_params
                        if s.param_name != self.param_name
                    ),
                    OpenSlot(
                        criterion_id=criterion.id,
                        param_name=self.param_name,
                        param_kind=bound.value.type,
                        options=self._offered(bound),
                    ),
                ],
                "result_count": None,
            }
        )


def _unsettled(criterion: Criterion, picks: Sequence[PickRead]) -> list[PickRead]:
    return [
        read
        for read in picks
        if read.search_name == criterion.search_name
        and not read.pick.settled
        and (bound := criterion.resolved_params.get(read.param_name)) is not None
        and bound.source == "chosen"
    ]


def unsettled_questions(
    criteria: Sequence[Criterion],
    picks: Sequence[PickRead],
    asked: Sequence[SlotQuestion],
) -> list[SlotQuestion]:
    held = {(q.criterion_id, q.param_name) for q in asked}
    return [
        read.question(criterion)
        for criterion in criteria
        for read in _unsettled(criterion, picks)
        if (criterion.id, read.param_name) not in held
    ]


def spec_held_open(spec: OperationalSpec, picks: Sequence[PickRead]) -> OperationalSpec:
    return spec.model_copy(
        update={
            "criteria": [
                reduce(
                    lambda held, read: read.reopened(held),
                    _unsettled(criterion, picks),
                    criterion,
                )
                for criterion in spec.criteria
            ]
        }
    )


__all__ = ["PickRead", "spec_held_open", "unsettled_questions"]
