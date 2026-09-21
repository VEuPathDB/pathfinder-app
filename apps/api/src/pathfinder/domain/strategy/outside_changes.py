"""What the strategy gained, lost and moved since it last answered to a spec.

Both sides are trees, so the comparison is graph against graph: a spec value
and a step value are different forms and are never compared to each other.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from veupathdb.domain.strategy import StrategyAst

from pathfinder.domain.strategy.ast_diff import (
    StepChange,
    StepSummary,
    diff_strategy_asts,
    nodes_of,
)
from pathfinder.domain.strategy.operational_spec import SpecStructure
from pathfinder.domain.strategy.spec_hydration import spec_from_ast

__all__ = ["OutsideChanges", "outside_changes"]


class OutsideChanges(BaseModel):
    """The difference between the answered tree and the live one."""

    model_config = ConfigDict(frozen=True)

    changed: list[StepChange] = Field(default_factory=list)
    added: list[StepSummary] = Field(default_factory=list)
    removed: list[StepSummary] = Field(default_factory=list)
    # Whether the shape derived from the two trees differs, which covers a
    # rewire, an operator and a restated join.
    structure_moved: bool = False

    @property
    def moved(self) -> bool:
        return bool(self.changed or self.added or self.removed or self.structure_moved)

    @property
    def removed_ids(self) -> frozenset[str]:
        return frozenset(step.step_id for step in self.removed)


def _structure_of(ast: StrategyAst) -> SpecStructure | None:
    return spec_from_ast(ast, goal="").structure


def outside_changes(
    answered: StrategyAst | None, live: StrategyAst | None
) -> OutsideChanges:
    """Compare the tree a spec answers to with the tree the strategy holds.

    A thread with no answered tree reports nothing, because nothing says what
    it was. An empty strategy removes every step the answered tree held.
    """
    if answered is None:
        return OutsideChanges()
    if live is None:
        return OutsideChanges(
            removed=[
                StepSummary(step_id=node.id, label=node.display_label)
                for node in nodes_of(answered).values()
            ],
            structure_moved=True,
        )
    diff = diff_strategy_asts(answered, live)
    return OutsideChanges(
        changed=diff.changed,
        added=diff.added,
        removed=diff.removed,
        structure_moved=_structure_of(answered) != _structure_of(live),
    )
