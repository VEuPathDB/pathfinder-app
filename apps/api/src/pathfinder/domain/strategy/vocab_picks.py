from __future__ import annotations

from collections.abc import Sequence

from pydantic import ConfigDict, Field
from veupathdb.domain.parameters import VocabOption
from veupathdb.model import CamelModel
from veupathdb_mcp.catalog import VocabPick

from pathfinder.domain.strategy.constraint_grounding import dimension_of_parameter
from pathfinder.domain.strategy.operational_spec import Criterion
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

    def question(self, criterion: Criterion) -> SlotQuestion:
        named = criterion.display_name_of(self.param_name)
        bound = criterion.resolved_params[self.param_name]
        offered = [
            *([] if self.pick.value is None else [self.pick.value]),
            *pick_terms(bound.value),
            *(option.value for option in self.kept),
        ]
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
            options=list(dict.fromkeys(offered))[:_OFFERED],
            criterion_id=criterion.id,
            param_name=self.param_name,
            labels={option.value: option.display for option in self.kept},
        )


def unsettled_questions(
    criteria: Sequence[Criterion],
    picks: Sequence[PickRead],
    asked: Sequence[SlotQuestion],
) -> list[SlotQuestion]:
    held = {(q.criterion_id, q.param_name) for q in asked}
    return [
        read.question(criterion)
        for criterion in criteria
        for read in picks
        if read.search_name == criterion.search_name
        and not read.pick.settled
        and (criterion.id, read.param_name) not in held
        and (bound := criterion.resolved_params.get(read.param_name)) is not None
        and bound.source == "chosen"
    ]


__all__ = ["PickRead", "unsettled_questions"]
